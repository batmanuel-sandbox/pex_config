#
# LSST Data Management System
# Copyright 2008-2013 LSST Corporation.
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
# see <http://www.lsstcorp.org/LegalNotices/>.
#
from builtins import str

from .config import Config, Field, FieldValidationError, _joinNamePath, _typeStr
from .comparison import compareConfigs, getComparisonName
from .callStack import getCallStack, getStackFrame

__all__ = ["ConfigField"]


class ConfigField(Field):
    """Configuration field that takes a `lsst.pex.config.Config`-type as a value.

    Parameters
    ----------
    doc : `str`
        Documentation string that describes the configuration field.
    dtype : `lsst.pex.config.Config`-type
        The type of the field, which must be a subclass of `lsst.pex.config.Config`.
    default : optional
        Description
        If default=None, the field will default to a default-constructed
        instance of dtype.
        Additionally, to allow for fewer deep-copies, assigning an instance of
        ConfigField to dtype itself, is considered equivalent to assigning a
        default-constructed sub-config. This means that the argument default can be
        dtype, as well as an instance of dtype.
        FIXME
    check : optional
        Description

    Notes
    -----
    The behavior of this type of field is much like that of the base `Field` type.

    Assigning to ``ConfigField`` will update all of the fields in the configuration.
    """

    def __init__(self, doc, dtype, default=None, check=None):
        if not issubclass(dtype, Config):
            raise ValueError("dtype=%s is not a subclass of Config" %
                             _typeStr(dtype))
        if default is None:
            default = dtype
        source = getStackFrame()
        self._setup(doc=doc, dtype=dtype, default=default, check=check,
                    optional=False, source=source)

    def __get__(self, instance, owner=None):
        if instance is None or not isinstance(instance, Config):
            return self
        else:
            value = instance._storage.get(self.name, None)
            if value is None:
                at = getCallStack()
                at.insert(0, self.source)
                self.__set__(instance, self.default, at=at, label="default")
            return value

    def __set__(self, instance, value, at=None, label="assignment"):
        if instance._frozen:
            raise FieldValidationError(self, instance,
                                       "Cannot modify a frozen Config")
        name = _joinNamePath(prefix=instance._name, name=self.name)

        if value != self.dtype and type(value) != self.dtype:
            msg = "Value %s is of incorrect type %s. Expected %s" % \
                (value, _typeStr(value), _typeStr(self.dtype))
            raise FieldValidationError(self, instance, msg)

        if at is None:
            at = getCallStack()

        oldValue = instance._storage.get(self.name, None)
        if oldValue is None:
            if value == self.dtype:
                instance._storage[self.name] = self.dtype(__name=name, __at=at, __label=label)
            else:
                instance._storage[self.name] = self.dtype(__name=name, __at=at,
                                                          __label=label, **value._storage)
        else:
            if value == self.dtype:
                value = value()
            oldValue.update(__at=at, __label=label, **value._storage)
        history = instance._history.setdefault(self.name, [])
        history.append(("config value set", at, label))

    def rename(self, instance):
        value = self.__get__(instance)
        value._rename(_joinNamePath(instance._name, self.name))

    def save(self, outfile, instance):
        value = self.__get__(instance)
        value._save(outfile)

    def freeze(self, instance):
        value = self.__get__(instance)
        value.freeze()

    def toDict(self, instance):
        value = self.__get__(instance)
        return value.toDict()

    def validate(self, instance):
        value = self.__get__(instance)
        value.validate()

        if self.check is not None and not self.check(value):
            msg = "%s is not a valid value" % str(value)
            raise FieldValidationError(self, instance, msg)

    def _compare(self, instance1, instance2, shortcut, rtol, atol, output):
        """Compare two fields for equality.

        Used by `ConfigField.compare`.

        Parameters
        ----------
        instance1 : `lsst.pex.config.Config`
            Left-hand side config instance to compare.
        instance2 : `lsst.pex.config.Config`
            Right-hand side config instance to compare.
        shortcut : `bool`
            If `True`, this function returns as soon as an inequality if found.
        rtol : `float`
            Relative tolerance for floating point comparisons.
        atol : `float`
            Absolute tolerance for floating point comparisons.
        output : callable
            A callable that takes a string, used (possibly repeatedly) to report inequalities.

        Returns
        -------
        isEqual : bool
            `True` if the fields are equal, `False` otherwise.

        Notes
        -----
        Floating point comparisons are performed by `numpy.allclose`.
        """
        c1 = getattr(instance1, self.name)
        c2 = getattr(instance2, self.name)
        name = getComparisonName(
            _joinNamePath(instance1._name, self.name),
            _joinNamePath(instance2._name, self.name)
        )
        return compareConfigs(name, c1, c2, shortcut=shortcut, rtol=rtol, atol=atol, output=output)
