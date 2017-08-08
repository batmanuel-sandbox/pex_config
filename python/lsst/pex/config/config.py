#
# LSST Data Management System
# Copyright 2008-2015 AURA/LSST.
#
# This product includes software developed by the
# LSST Project (http://www.lsst.org/).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the LSST License Statement and
# the GNU General Public License along with this program.  If not,
# see <https://www.lsstcorp.org/LegalNotices/>.
#
oldStringType = str  # Need to keep hold of original str type
from builtins import str
from builtins import object
from past.builtins import long
from past.builtins import basestring
from past.builtins import unicode

import os
import io
import sys
import math
import copy
import tempfile
import shutil

from .comparison import getComparisonName, compareScalars, compareConfigs
from .callStack import getStackFrame, getCallStack
from future.utils import with_metaclass

__all__ = ("Config", "Field", "FieldValidationError")


def _joinNamePath(prefix=None, name=None, index=None):
    """Generate nested configuration names.
    """
    if not prefix and not name:
        raise ValueError("Invalid name: cannot be None")
    elif not name:
        name = prefix
    elif prefix and name:
        name = prefix + "." + name

    if index is not None:
        return "%s[%r]" % (name, index)
    else:
        return name


def _autocast(x, dtype):
    """Cast a value to a type, if appropriate.

    Parameters
    ----------
    x : object
        A value.
    dtype : class
        Data type, such as `float`, `int`, or `str`.

    Returns
    -------
    values : object
        If appropriate, the returned value is ``x`` cast to the given type ``dtype``. If the cast cannot
        be performed the original value of ``x`` is returned.
    """
    if dtype == float and isinstance(x, int):
        return float(x)
    if dtype == int and isinstance(x, long):
        return int(x)
    if isinstance(x, str):
        return oldStringType(x)
    return x


def _typeStr(x):
    """Generate a fully-qualified type name.

    Returns
    -------
    typeStr : `str`
        Fully-qualified type name.

    Notes
    -----
    This is used primarily in writing config files to be executed later upon 'load'.
    """
    if hasattr(x, '__module__') and hasattr(x, '__name__'):
        xtype = x
    else:
        xtype = type(x)
    if (sys.version_info.major <= 2 and xtype.__module__ == '__builtin__') or xtype.__module__ == 'builtins':
        return xtype.__name__
    else:
        return "%s.%s" % (xtype.__module__, xtype.__name__)


class ConfigMeta(type):
    """Metaclass for `lsst.pex.config.Config`.

    Notes
    -----
    Adds a dictionary containing all Field class attributes as a class attribute called ``_fields``, and adds
    the name of each field as an instance variable of the field itself (so you don't have to pass the name of
    the field to the field constructor).
    """

    def __init__(self, name, bases, dict_):
        type.__init__(self, name, bases, dict_)
        self._fields = {}
        self._source = getStackFrame()

        def getFields(classtype):
            fields = {}
            bases = list(classtype.__bases__)
            bases.reverse()
            for b in bases:
                fields.update(getFields(b))

            for k, v in classtype.__dict__.items():
                if isinstance(v, Field):
                    fields[k] = v
            return fields

        fields = getFields(self)
        for k, v in fields.items():
            setattr(self, k, copy.deepcopy(v))

    def __setattr__(self, name, value):
        if isinstance(value, Field):
            value.name = name
            self._fields[name] = value
        type.__setattr__(self, name, value)


class FieldValidationError(ValueError):
    """Exception class which holds additional information, as attributes, useful for debugging
    `lsst.pex.config.Config` errors.
    """

    """Type of the `~lsst.pex.config.Field` that incurred the error (class)."""
    fieldType = None

    """Name of the `~lsst.pex.config.Field` instance that incurred the error (str).

    See also
    --------
    lsst.pex.config.Field.name
    """
    fieldName = None

    """Fully-qualified name of the `~lsst.pex.config.Field` instance (`str`)."""
    fullname = None

    """Full history of all changes to the `~lsst.pex.config.Field` instance."""
    history = None

    """File and line number of the `~lsst.pex.config.Field` definition."""
    fieldSource = None

    def __init__(self, field, config, msg):
        self.fieldType = type(field)
        self.fieldName = field.name
        self.fullname = _joinNamePath(config._name, field.name)
        self.history = config.history.setdefault(field.name, [])
        self.fieldSource = field.source
        self.configSource = config._source
        error = "%s '%s' failed validation: %s\n"\
                "For more information read the Field definition at:\n%s"\
                "And the Config definition at:\n%s" % \
            (self.fieldType.__name__, self.fullname, msg,
             self.fieldSource.format(), self.configSource.format())
        ValueError.__init__(self, error)


class Field(object):
    """Configuration field.

    Parameters
    ----------
    doc : `str`
        Documentation string for the field.
    dtype : class
        Data type for the field.
    default : object, optional
        Default value for the field.
    check : callable, optional
        A callable to be called with the field value that returns `False` if the value is invalid. More
        complex inter-field validation can be written as part of the `lsst.pex.config.Config.validate`
        method.
    optional : `bool`, optional
        When `False`, `lsst.pex.config.Config.validate` will fail if the field's value is `None`.

    Raises
    ------
    ValueError
        Raised when the ``dtype`` parameter is not one of the supported types (see `Field.supportedTypes`).

    Notes
    -----
    Field only supports basic data types (`int`, `float`, `complex`, `bool`, `str`, `unicode`).
    See `Field.supportedTypes`.

    Examples
    --------
    Instances of ``Field`` should be used as class attributes of `lsst.pex.config.Config` subclasses:

    >>> class Example(Config):
    >>>     myInt = Field(int, "an integer field!", default=0)
    """

    """Supported data types for field values."""
    supportedTypes = set((str, unicode, basestring, oldStringType, bool, float, int, complex))
    # Must be able to support str and future str as we can not guarantee that
    # code will pass in a future str type on Python 2

    def __init__(self, doc, dtype, default=None, check=None, optional=False):
        if dtype not in self.supportedTypes:
            raise ValueError("Unsupported Field dtype %s" % _typeStr(dtype))

        # Use standard string type if we are given a future str
        if dtype == str:
            dtype = oldStringType

        source = getStackFrame()
        self._setup(doc=doc, dtype=dtype, default=default, check=check, optional=optional, source=source)

    def _setup(self, doc, dtype, default, check, optional, source):
        """Initialization helper.
        """
        self.dtype = dtype
        self.doc = doc
        self.__doc__ = doc
        self.default = default
        self.check = check
        self.optional = optional
        self.source = source

    def rename(self, instance):
        """Rename an instance of this field.

        Parameters
        ----------
        instance
            Unknown.

        Note
        ----
        This is invoked by the owning `lsst.pex.config.Config` object and should not be called directly.

        Renaming is only relevant for `~lsst.pex.config.Field`\ s that hold subconfigs.
        `~lsst.pex.config.Fields` that hold subconfigs should rename each subconfig with the full field name
        as generated by `lsst.pex.config.config._joinNamePath`.
        """
        pass

    def validate(self, instance):
        """Validate the field.

        Parameters
        ----------
        instance
            Unknown.

        Raises
        ------
        lsst.pex.config.FieldValidationError
            Raised if verification fails.

        Notes
        -----
        This method provides basic validation:

        - Ensures that non-optional fields are not `None`.
        - Ensures type correctness.
        - Ensures that the user-provided ``check`` function is valid.

        FIXME: is type checking and validation of ``check`` actually performed?

        Most `lsst.pex.config.Field` subclasses should call `lsst.pex.config.field.Field.validate` if they
        choose to re-implement `~lsst.pex.config.field.Field.validate`.
        """
        value = self.__get__(instance)
        if not self.optional and value is None:
            raise FieldValidationError(self, instance, "Required value cannot be None")

    def freeze(self, instance):
        """Make this field read-only.

        Parameters
        ----------
        instance
            Unknown.

        Notes
        -----
        Freezing is only relevant for fields that hold subconfigs. Fields which hold subconfigs should freeze
        each subconfig.

        **Subclasses should implement this method.**
        """
        pass

    def _validateValue(self, value):
        """Validate a value.

        Parameters
        ----------
        instance
            Unknown.

        Notes
        -----
        FIXME: is this statement true?
        This is called from __set__
        This is not part of the Field API. However, simple derived field types
            may benifit from implementing _validateValue
        """
        if value is None:
            return

        if not isinstance(value, self.dtype):
            msg = "Value %s is of incorrect type %s. Expected type %s" % \
                (value, _typeStr(value), _typeStr(self.dtype))
            raise TypeError(msg)
        if self.check is not None and not self.check(value):
            msg = "Value %s is not a valid value" % str(value)
            raise ValueError(msg)

    def save(self, outfile, instance):
        """Save an instance of this field to a file.

        Parameters
        ----------
        outfile : file-like object
            A writeable field handle.
        instance
            Unkown.

        Notes
        -----
        This is invoked by the owning `lsst.pex.config.Config` object and should not be called directly.

        The output consists of the documentation string (`lsst.pex.config.Field.doc`), prefixed with a
        ``# `` (to make a Python comment). The second line is formatted as ``{fullname}={value}``.
        """
        value = self.__get__(instance)
        fullname = _joinNamePath(instance._name, self.name)

        # write full documentation string as comment lines (i.e. first character is #)
        doc = "# " + str(self.doc).replace("\n", "\n# ")
        if isinstance(value, float) and (math.isinf(value) or math.isnan(value)):
            # non-finite numbers need special care
            outfile.write(u"{}\n{}=float('{!r}')\n\n".format(doc, fullname, value))
        else:
            outfile.write(u"{}\n{}={!r}\n\n".format(doc, fullname, value))

    def toDict(self, instance):
        """Convert the field value so that it can be set as the value of an item in a `dict`.

        Parameters
        ----------
        instance
            Unknown.

        Returns
        -------
        value
            Unkown.

        Notes
        -----
        This is invoked by the owning `lsst.pex.config.Config` object and should not be called directly.

        Simple values are passed through. Complex data structures must be manipulated. For example, a
        `~lsst.pex.config.Field` holding a subconfig should, instead of the subconfig object, return a `dict`
        where the keys are the field names in the subconfig, and the values are the field values in the
        subconfig.

        See also
        --------
        lsst.pex.config.Field.toDict
        """
        return self.__get__(instance)

    def __get__(self, instance, owner=None, at=None, label="default"):
        """
        Define how attribute access should occur on the Config instance
        This is invoked by the owning config object and should not be called
        directly

        When the field attribute is accessed on a Config class object, it
        returns the field object itself in order to allow inspection of
        Config classes.

        When the field attribute is access on a config instance, the actual
        value described by the field (and held by the Config instance) is
        returned.
        """
        if instance is None or not isinstance(instance, Config):
            return self
        else:
            return instance._storage[self.name]

    def __set__(self, instance, value, at=None, label='assignment'):
        """Set an attribute on the config instance.

        Parameters
        ----------
        instance
            Unknown.
        value
            Unknown.
        at : optional
            Unkown.
        label : `str`, optional
            Unknown.

        Notes
        -----
        This method is invoked by the owning `lsst.pex.config.Config` object and should not be called
        directly.

        Derived `~lsst.pex.config.Field` classes may need to override the behavior. When overriding
        ``__set__``, `~lsst.pex.config.Field` authors should follow the following rules:

        - Do not allow modification of frozen configs.
        - Validate the new value **before** modifying the field. Except if the new value is `None`. `None`
          is special and no attempt should be made to validate it until `lsst.pex.config.Config.validate` is
          called.
        - Do not modify the `~lsst.pex.config.Config` instance to contain invalid values.
        - If the field is modified, update the history of the `lsst.pex.config.field.Field` to reflect the
          changes.

        In order to decrease the need to implement this method in derived `~lsst.pex.config.Field` types,
        value validation is performed in the `lsst.pex.config.Field._validateValue`. If only the validation
        step differs in the derived `~lsst.pex.config.Field`, it is simpler to implement
        `lsst.pex.config.Field._validateValue` than to reimplement ``__set__``. More complicated
        behavior, however, may require reimplementation.
        """
        if instance._frozen:
            raise FieldValidationError(self, instance, "Cannot modify a frozen Config")

        history = instance._history.setdefault(self.name, [])
        if value is not None:
            value = _autocast(value, self.dtype)
            try:
                self._validateValue(value)
            except BaseException as e:
                raise FieldValidationError(self, instance, str(e))

        instance._storage[self.name] = value
        if at is None:
            at = getCallStack()
        history.append((value, at, label))

    def __delete__(self, instance, at=None, label='deletion'):
        """Delete an attribute from a `lsst.pex.config.Config` instance.

        Parameters
        ----------
        instance
            Unknown.
        at : optional
            Unkown.
        label : `str`, optional
            Unknown.

        Notes
        -----
        This is invoked by the owning `~lsst.pex.config.Config` object and should not be called directly.
        """
        if at is None:
            at = getCallStack()
        self.__set__(instance, None, at=at, label=label)

    def _compare(self, instance1, instance2, shortcut, rtol, atol, output):
        """Compare two fields for equality.

        Parameters
        ----------
        instance1 : `lsst.pex.config.Config`
            Left-hand side config instance to compare.
        instance2 : `lsst.pex.config.Config`
            Right-hand side config instance to compare.
        shortcut : `bool`, optional
            **Unused.**
        rtol : `float`, optional
            Relative tolerance for floating point comparisons.
        atol : `float`, optional
            Absolute tolerance for floating point comparisons.
        output : callable, optional
            A callable that takes a string, used (possibly repeatedly) to report inequalities.

        Notes
        -----
        This method must be overridden by more complex field types.

        FIXME why is this method calling compareScalars rather than compareConfigs?

        See also
        --------
        lsst.pex.config.compareScalars
        """
        v1 = getattr(instance1, self.name)
        v2 = getattr(instance2, self.name)
        name = getComparisonName(
            _joinNamePath(instance1._name, self.name),
            _joinNamePath(instance2._name, self.name)
        )
        return compareScalars(name, v1, v2, dtype=self.dtype, rtol=rtol, atol=atol, output=output)


class RecordingImporter(object):
    """Importer (for `sys.meta_path`) that records which modules are being imported.

    Notes
    -----
    This class makes no effort to do any importing itself.

    Use this class as a context manager to ensure it is properly uninstalled when done. See *Examples*.


    Examples
    --------
    Objects also act as context managers. For example:

    >>> with RecordingImporter() as importer:
    >>>     # import stuff
    >>>     import numpy as np
    >>> print("Imported: " + importer.getModules())
    """

    def __init__(self):
        self._modules = set()

    def __enter__(self):
        self.origMetaPath = sys.meta_path
        sys.meta_path = [self] + sys.meta_path
        return self

    def __exit__(self, *args):
        self.uninstall()
        return False  # Don't suppress exceptions

    def uninstall(self):
        """Uninstall the Importer."""
        sys.meta_path = self.origMetaPath

    def find_module(self, fullname, path=None):
        """Called as part of the 'import' chain of events.
        """
        self._modules.add(fullname)
        # Return None because we don't do any importing.
        return None

    def getModules(self):
        """Get the set of modules that were imported.

        Returns
        -------
        modules
            Unkown.
        """
        return self._modules


class Config(with_metaclass(ConfigMeta, object)):
    """Base configuration class.

    Notes
    -----
    A Config object will usually have several `~lsst.pex.config.Field` instances as class attributes. These
    are used to define most of the base class behavior. Simple derived class should be able to be defined
    simply by setting those attributes.

    Config implements a mapping API that provides key-value access to fields and `dict`-like methods.
    """

    def __iter__(self):
        """Iterate over fields.
        """
        return self._fields.__iter__()

    def keys(self):
        """Get field names.

        Returns
        -------
        names : `list`
            List of `lsst.pex.config.Field` names.

        See also
        --------
        lsst.pex.config.Config.iterkeys
        """
        return list(self._storage.keys())

    def values(self):
        """Get field values.

        Returns
        -------
        values : `list`
            List of field values.

        See also
        --------
        lsst.pex.config.Config.itervalues
        """
        return list(self._storage.values())

    def items(self):
        """Get configurations as ``(field name, field value)`` pairs.

        Returns
        -------
        items : `list`
            List of tuples for each configuration. Tuple items are:

            - Field name.
            - Field value.

        See also
        --------
        lsst.pex.config.Config.iteritems
        """
        return list(self._storage.items())

    def iteritems(self):
        """Iterate over (field name, field value) pairs.

        See also
        --------
        lsst.pex.config.Config.items
        """
        return iter(self._storage.items())

    def itervalues(self):
        """Iterate over field values.

        See also
        --------
        lsst.pex.config.Config.values
        """
        return iter(self.storage.values())

    def iterkeys(self):
        """Iterate over field names

        See also
        --------
        lsst.pex.config.Config.values
        """
        return iter(self.storage.keys())

    def __contains__(self, name):
        """!Return True if the specified field exists in this config

        @param[in] name  field name to test for
        """
        return self._storage.__contains__(name)

    def __new__(cls, *args, **kw):
        """Allocate a new `lsst.pex.config.Config` object.

        In order to ensure that all Config object are always in a proper state when handed to users or to
        derived `~lsst.pex.config.Config` classes, some attributes are handled at allocation time rather than
        at initialization.

        This ensures that even if a derived `~lsst.pex.config.Config` class implements __init__, its author
        does not need to be concerned about when or even the base ``Config.__init__`` should be called.
        """
        name = kw.pop("__name", None)
        at = kw.pop("__at", getCallStack())
        # remove __label and ignore it
        kw.pop("__label", "default")

        instance = object.__new__(cls)
        instance._frozen = False
        instance._name = name
        instance._storage = {}
        instance._history = {}
        instance._imports = set()
        # load up defaults
        for field in instance._fields.values():
            instance._history[field.name] = []
            field.__set__(instance, field.default, at=at + [field.source], label="default")
        # set custom default-overides
        instance.setDefaults()
        # set constructor overides
        instance.update(__at=at, **kw)
        return instance

    def __reduce__(self):
        """Reduction for pickling (function with arguments to reproduce).

        We need to condense and reconstitute the `~lsst.pex.config.Config`, since it may contain lambdas
        (as the ``check`` elements) that cannot be pickled.
        """
        # The stream must be in characters to match the API but pickle requires bytes
        stream = io.StringIO()
        self.saveToStream(stream)
        return (unreduceConfig, (self.__class__, stream.getvalue().encode()))

    def setDefaults(self):
        """Subclass hook for computing defaults.

        Notes
        -----
        Derived `~lsst.pex.config.Config` classes that must compute defaults rather than using the
        `lsst.pex.config.Field`\ s's defaults should do so here. To correctly use inherited defaults,
        implementations of ``setDefaults`` must call their base class's ``setDefaults``.
        """
        pass

    def update(self, **kw):
        """Update values specified by the keyword arguments.

        Parameters
        ----------
        kw
            Keywords are configuration field names. Values are configuration field values.

        Notes
        -----
        The ``__at`` and ``__label`` keyword arguments are special internal keywords. They are used to strip
        out any internal steps from the history tracebacks of the config. Do not modify these keywords to
        subvert a `~lsst.pex.config.Config`\ ’s history.
        """
        at = kw.pop("__at", getCallStack())
        label = kw.pop("__label", "update")

        for name, value in kw.items():
            try:
                field = self._fields[name]
                field.__set__(self, value, at=at, label=label)
            except KeyError:
                raise KeyError("No field of name %s exists in config type %s" % (name, _typeStr(self)))

    def load(self, filename, root="config"):
        """Modify this Config in place by executing the Python code in a configuration file.

        Parameters
        ----------
        filename : `str`
            Name of the configuration file. A configuration file is Python module.
        root : `str`, optional
            Name of the variable in file that refers to the config being overridden.

            For example, the value of root is ``"config"`` and the file contains::

                config.myField = 5

            Then this config's field ``"myField"`` is set to ``5``.

            **Deprecated:** For backwards compatibility, older config files that use ``root="root"`` instead
            of ``root="config"`` will be loaded with a warning printed to `sys.stderr`. This feature will be
            removed at some point.

        See also
        --------
        lsst.pex.config.Config.loadFromStream
        lsst.pex.config.Config.save
        lsst.pex.config.Config.saveFromStream
        """
        with open(filename, "r") as f:
            code = compile(f.read(), filename=filename, mode="exec")
            self.loadFromStream(stream=code, root=root)

    def loadFromStream(self, stream, root="config", filename=None):
        """Modify this Config in place by executing the Python code in the provided stream.

        Parameters
        ----------
        stream : file-like object, `str`, or compiled string
            Stream containing configuration override code.
        root : `str`, optional
            Name of the variable in file that refers to the config being overridden.

            For example, the value of root is ``"config"`` and the file contains::

                config.myField = 5

            Then this config's field ``"myField"`` is set to ``5``.

            **Deprecated:** For backwards compatibility, older config files that use ``root="root"`` instead
            of ``root="config"`` will be loaded with a warning printed to `sys.stderr`. This feature will be
            removed at some point.
        filename : optional
            Name of the configuration file, or `None` if unknown or contained in the stream. Used for error
            reporting.

        See also
        --------
        lsst.pex.config.Config.load
        lsst.pex.config.Config.save
        lsst.pex.config.Config.saveFromStream
        """
        with RecordingImporter() as importer:
            try:
                local = {root: self}
                exec(stream, {}, local)
            except NameError as e:
                if root == "config" and "root" in e.args[0]:
                    if filename is None:
                        # try to determine the file name; a compiled string has attribute "co_filename",
                        # an open file has attribute "name", else give up
                        filename = getattr(stream, "co_filename", None)
                        if filename is None:
                            filename = getattr(stream, "name", "?")
                    sys.stderr.write(u"Config override file %r" % (filename,) +
                                     u" appears to use 'root' instead of 'config'; trying with 'root'")
                    local = {"root": self}
                    exec(stream, {}, local)
                else:
                    raise

        self._imports.update(importer.getModules())

    def save(self, filename, root="config"):
        """Save a Python script to the named file, which, when loaded, reproduces this Config.

        Parameters
        ----------
        filename : `str`
            Desination filename of this configuration.
        root
            Name to use for the root config variable. The same value must be used when loading (see
            `lsst.pex.config.Config.load`).

        See also
        --------
        lsst.pex.config.Config.saveToStream
        lsst.pex.config.Config.load
        lsst.pex.config.Config.loadFromStream
        """
        d = os.path.dirname(filename)
        with tempfile.NamedTemporaryFile(mode="w", delete=False, dir=d) as outfile:
            self.saveToStream(outfile, root)
            # tempfile is hardcoded to create files with mode '0600'
            # for an explantion of these antics see:
            # https://stackoverflow.com/questions/10291131/how-to-use-os-umask-in-python
            umask = os.umask(0o077)
            os.umask(umask)
            os.chmod(outfile.name, (~umask & 0o666))
            # chmod before the move so we get quasi-atomic behavior if the
            # source and dest. are on the same filesystem.
            # os.rename may not work across filesystems
            shutil.move(outfile.name, filename)

    def saveToStream(self, outfile, root="config"):
        """Save a configuration file to a stream, which, when loaded, reproduces this Config.

        Parameters
        ----------
        outfile : file-like object
            Destination file object write the config into. Accepts strings not bytes.
        root
            Name to use for the root config variable. The same value must be used when loading (see
            `lsst.pex.config.Config.load`).

        See also
        --------
        lsst.pex.config.Config.save
        lsst.pex.config.Config.load
        lsst.pex.config.Config.loadFromStream
        """
        tmp = self._name
        self._rename(root)
        try:
            configType = type(self)
            typeString = _typeStr(configType)
            outfile.write(u"import {}\n".format(configType.__module__))
            outfile.write(u"assert type({})=={}, 'config is of type %s.%s ".format(root, typeString))
            outfile.write(u"instead of {}' % (type({}).__module__, type({}).__name__)\n".format(typeString,
                                                                                                root,
                                                                                                root))
            self._save(outfile)
        finally:
            self._rename(tmp)

    def freeze(self):
        """Make this `~lsst.pex.config.Config` and all subconfigs read-only.
        """
        self._frozen = True
        for field in self._fields.values():
            field.freeze(self)

    def _save(self, outfile):
        """Save this Config to an open stream object.

        Parameters
        ----------
        outfile : file-like object
            Destination file object write the config into. Accepts strings not bytes.
        """
        for imp in self._imports:
            if imp in sys.modules and sys.modules[imp] is not None:
                outfile.write(u"import {}\n".format(imp))
        for field in self._fields.values():
            field.save(outfile, self)

    def toDict(self):
        """Make a dictionary of field names and their values.

        Returns
        -------
        dict_ : `dict`
            Dictionary with keys that are `~lsst.pex.config.Field` names. Values are `~lsst.pex.config.Field`
            values.

        Notes
        -----
        This method uses the `~lsst.pex.config.Field.toDict` method of individual `lsst.pex.config.Field`\ s.
        Custom `lsst.pex.config.Field`-types may need to implement a ``toDict`` method for *this* method to
        work.

        See also
        --------
        lsst.pex.config.Field.toDict
        """
        dict_ = {}
        for name, field in self._fields.items():
            dict_[name] = field.toDict(self)
        return dict_

    def _rename(self, name):
        """Rename this Config object in its parent `lsst.pex.config.Config`.

        Parameters
        ----------
        name : `str`
            New name for this Config in its parent Config.

        Notes
        -----
        This method uses the `~lsst.pex.config.Field.rename` method of individual `lsst.pex.config.Field`\ s.
        Custom `lsst.pex.config.Field`-types may need to implement a ``rename`` method for *this* method to
        work.

        See also
        --------
        lsst.pex.config.Field.rename
        """
        self._name = name
        for field in self._fields.values():
            field.rename(self)

    def validate(self):
        """Validate the Config, raising an exception if invalid.

        Raises
        ------
        lsst.pex.config.FieldValidationError
            Raised if verification fails.

        Notes
        -----
        The base class implementation performs type checks on all fields by calling their
        `~lsst.pex.config.Field.validate` methods.

        Complex single-field validation can be defined by deriving new Field types. For convenience, some
        derived `lsst.pex.config.Field`-types (`~lsst.pex.config.ConfigField` and
        `~lsst.pex.config.ConfigChoiceField`) are defined in `lsst.pex.config` that handle recursing into
        subconfigs.

        Inter-field relationships should only be checked in derived `~lsst.pex.config.Config` classes after
        calling this method, and base validation is complete.
        """
        for field in self._fields.values():
            field.validate(self)

    def formatHistory(self, name, **kwargs):
        """Format a configuration field's history to a human-readable format.

        Parameters
        ----------
        name : `str`
            Name of a `~lsst.pex.config.Field`.
        kwargs
            Keyword arguments passed to `lsst.pex.config.history.format`.

        Returns
        -------
        history : `str`
            A string containing the formatted history.

        See also
        --------
        lsst.pex.config.history.format
        """
        import lsst.pex.config.history as pexHist
        return pexHist.format(self, name, **kwargs)

    """Read-only history.
    """
    history = property(lambda x: x._history)

    def __setattr__(self, attr, value, at=None, label="assignment"):
        """Set an attribute.

        Notes
        -----
        Unlike normal Python objects, `~lsst.pex.config.Config` objects are locked such that no additional
        attributes nor properties may be added to them dynamically.

        Although this is not the standard Python behavior, it helps to protect users from accidentally
        mispelling a field name, or trying to set a non-existent field.
        """
        if attr in self._fields:
            if at is None:
                at = getCallStack()
            # This allows Field descriptors to work.
            self._fields[attr].__set__(self, value, at=at, label=label)
        elif hasattr(getattr(self.__class__, attr, None), '__set__'):
            # This allows properties and other non-Field descriptors to work.
            return object.__setattr__(self, attr, value)
        elif attr in self.__dict__ or attr in ("_name", "_history", "_storage", "_frozen", "_imports"):
            # This allows specific private attributes to work.
            self.__dict__[attr] = value
        else:
            # We throw everything else.
            raise AttributeError("%s has no attribute %s" % (_typeStr(self), attr))

    def __delattr__(self, attr, at=None, label="deletion"):
        if attr in self._fields:
            if at is None:
                at = getCallStack()
            self._fields[attr].__delete__(self, at=at, label=label)
        else:
            object.__delattr__(self, attr)

    def __eq__(self, other):
        if type(other) == type(self):
            for name in self._fields:
                thisValue = getattr(self, name)
                otherValue = getattr(other, name)
                if isinstance(thisValue, float) and math.isnan(thisValue):
                    if not math.isnan(otherValue):
                        return False
                elif thisValue != otherValue:
                    return False
            return True
        return False

    def __ne__(self, other):
        return not self.__eq__(other)

    def __str__(self):
        return str(self.toDict())

    def __repr__(self):
        return "%s(%s)" % (
            _typeStr(self),
            ", ".join("%s=%r" % (k, v) for k, v in self.toDict().items() if v is not None)
        )

    def compare(self, other, shortcut=True, rtol=1E-8, atol=1E-8, output=None):
        """Compare this configuration to another `~lsst.pex.config.Config` for equality.

        Parameters
        ----------
        other : `lsst.pex.config.Config`
            Other `~lsst.pex.config.Config` object to compare with self.
        shortcut : `bool`, optional
            If `True`, return as soon as an inequality is found. Default is `True`.
        rtol : `float`, optional
            Relative tolerance for floating point comparisons.
        atol : `float`, optional
            Absolute tolerance for floating point comparisons.
        output : callable, optional
            A callable that takes a string, used (possibly repeatedly) to report inequalities.

        Returns
        -------
        isEqual : `bool`
            `True` when the two `lsst.pex.config.Config` instances are equal. `False` if there is an
            inequality.

        Notes
        -----
        If the `~lsst.pex.config.Configs` contain `~lsst.pex.config.RegistryField`\ s or
        `~lsst.pex.config.ConfigChoiceFields`, unselected Configs will not be compared.

        Floating point comparisons are performed by `numpy.allclose`.

        See also
        --------
        lsst.pex.config.compareConfigs
        """
        name1 = self._name if self._name is not None else "config"
        name2 = other._name if other._name is not None else "config"
        name = getComparisonName(name1, name2)
        return compareConfigs(name, self, other, shortcut=shortcut,
                              rtol=rtol, atol=atol, output=output)


def unreduceConfig(cls, stream):
    config = cls()
    config.loadFromStream(stream)
    return config
