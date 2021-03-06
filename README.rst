==========
pex_config
==========

Overview
========

The `pex_config` package provides for configurations for the LSST 
Data Management System.

Configurations are hierarchical trees of parameters used to control the
execution of code.  They should not be confused with input data.
`pex_config` configurations (`Config` objects) are validatable,
documentable, and recordable.  The configuration parameters are stored in
attributes (member variables) of type `Field` in the `Config` object. Their
values can be recorded for provenance purposes. The history of their changes
during program execution is also tracked, and can be recorded and examined for
provenance and debugging purposes.

`pex_config` is implemented in Python.  Python code is used both in defining
the available `Field`\ s and in setting or modifying their values.  This
provides great flexibility and introspection while still being approachable to
non-programmers who need to modify configuration settings.

Example
-------

Defining a configuration subclass::

    import lsst.pex.config as pexConfig
    
    class IsrTaskConfig(pexConfig.config):
        doWrite = pexConfig.Field("Write output?", bool, True)
        fwhm = pexConfig.Field("FWHM of PSF (arcsec)", float, 1.0)
        saturatedMaskName = pexConfig.Field(
            "Name of mask plane to use in saturation detection", str, "SAT")
        flatScalingType = pexConfig.ChoiceField(
            "The method for scaling the flat on the fly.", str,
            default='USER',
            allowed={
                "USER": "User defined scaling",
                "MEAN": "Scale by the inverse of the mean",
                "MEDIAN": "Scale by the inverse of the median",
            })
        keysToRemoveFromAssembledCcd = pexConfig.ListField(
            "fields to remove from the metadata of the assembled ccd.",
            dtype=str, default=[])

Here is a sample configuration override file to be used with the partial
``IsrTaskConfig`` above.  Note that all field names are prefixed with "root"
and that overrides should never be used to set already-existing default
values::

    root.doWrite = False
    root.fwhm = 0.8
    root.saturatedMaskName = 'SATUR'
    root.flatScalingType = 'MEAN'
    root.keysToRemoveFromAssembledCcd = ['AMPNAME']

Typical usage::

    def doIsrTask(ccd, configOverrideFilename=None):
        config = IsrTaskConfig()
        if configOverrideFilename is not None:
            config.load(configOverrideFilename)
            # Note: config override files are Python code with .py extensions
            # by convention
        config.validate()
        config.freeze()

        detectSaturation(ccd, config.fwhm, config.saturatedMaskName)
        # Note: methods typically do not need the entire config; they should be
        # passed only relevant parameters
        for k in config.keysToRemoveFromAssembledCcd:
            ccd.metadata.remove(k)
        if config.doWrite:
            ccd.write()
    
Usage
-----

`pex_config` arose from a desire to have a configuration object holding
key-value pairs that also allows for (arbitrarily simple or complex) validation
of configuration values.

To configure code using `pex_config`, a developer subclasses the `Config`
class. The subclass definition specifies the available `Field`\ s, their
default values (if any), and their validation, if necessary.

`Config`\ s are hierarchical (see `ConfigField`), so calling code can embed
the configuration definitions of called code.

Configurations are *not* input data.  They should not be used in place of
function or method arguments, nor are they intended to replace ordinary
dictionary data structures.  A good rule of thumb is that if a particular
parameter does not have a useful default, it is probably an input rather than a
configuration parameter.  Another rule of thumb is that configuration
parameters should generally not be set in algorithmic code, only in
initialization or user interface code.

A `Config` subclass is instantiated to create a configuration object.  If any
default `Field` values need to be overridden, they can be set by assignment
to the object's `Field` attributes (e.g. `config.param1 = 3.14`), often in
a parent `Config`'s `setDefaults()` method, or by loading from an external
file.  The code then uses the configuration values by accessing the object's
`Field` attributes (e.g., `x = config.param1`).

The `Config` object can also be frozen; attempting to change the field
values of a frozen object will raise an exception. This is useful to 
expose bugs that change configuration values after none should happen.

Finally, the contents of `Config` objects may easily be dumped, for
provenance or debugging purposes.


Design Goals
------------

* Enable configuration of plug-in algorithms provided at runtime.

* Allow setting of one `Field` to affect the values and the validation of
  others.

* Collocate the `Config` definition with the code using the `Config`.

* Provide a "Pythonic" interface.

* Record the file and line of `Field` definitions and all changes to
  `Field`\ s, including setting default values.

* Set defaults before overriding with user-specified values.

* Support parameters with no (nonexistent) values, including overriding
  existing default values.

* Enable closely-related `Config`\ s to be represented efficiently, with
  a minimum of duplication.

* Have all user-modifiable `Config`\ s be part of a hierarchical tree.

* Validate the contents of `Field`\ s as soon as possible.

* Be able to "freeze" a `Config` to make it read-only.

* Be able to persist a `Config` to a file and restore it identically.

* Allow C++ control objects to be created from `Config`\ s, with documentation
  and validation specified exactly once.

* Support lists of parameter values.

See :wiki:`PolicyEnhancement` and :wiki:`Winter2012/PolicyRedesign`.


Details
=======

All `Config`\ s are (direct or indirect) subclasses of the Python class
`lsst.pex.config.Config`.  `Config`\ s may inherit from other `Config`\ s, in
which case all of the `Field`\ s of the parent class are present in the
subclass.

Each `Field` is required to have a doc string that describes the contents of
the field. Doc strings can be verbose and should give users of the `Config` a
good understanding of what the `Field` is and how it will be interpreted and
used.  A doc string should also be provided for the class as a whole.  The doc
strings for the class and its `Field`\ s may be inspected using
"`help(MyConfig)`" or with the `pydoc` command.

Types of `Field`\ s
-------------------

Attributes of the configuration object must be subclasses of
`pex_config.Field`.  A number of these are predefined (and documented in
doxygen_ and their class doc strings): `Field`, `RangeField`,
`ChoiceField`, `ListField`, `ConfigField`, `ConfigChoiceField`,
`RegistryField` and `ConfigurableField`.

.. _doxygen: http://lsst-web.ncsa.illinois.edu/doxygen/x_masterDoxyDoc/namespacelsst_1_1pex_1_1config.html

Example of `RangeField`::

    class BackgroundConfig(pexConfig.Config):
        """Parameters for controlling background estimation."""
        binSize = pexConfig.RangeField(
            doc="how large a region of the sky should be used for each background point",
            dtype=int, default=256, min=10
        )

Example of `ListField` and `Config` inheritance::

    class OutlierRejectedCoaddConfig(CoaddTask.ConfigClass):
        """Additional parameters for outlier-rejected coadds."""
        subregionSize = pexConfig.ListField(
            dtype = int,
            doc = """width, height of stack subregion size; make small enough that a full stack of images will fit into memory at once""",
            length = 2,
            default = (200, 200),
            optional = None,
        )

Examples of `ChoiceField` and `ConfigField` and the use of `Config`'s `setDefaults()` and `validate()` methods::

    class InitialPsfConfig(pexConfig.Config):
        """Describes the initial PSF used for detection and measurement before
        we do PSF determination."""

        model = pexConfig.ChoiceField(
            dtype = str,
            doc = "PSF model type",
            default = "SingleGaussian",
            allowed = {
                "SingleGaussian": "Single Gaussian model",
                "DoubleGaussian": "Double Gaussian model",
            },
        )

    class CalibrateConfig(pexConfig.Config):
        """Configure calibration of an exposure."""
        initialPsf = pexConfig.ConfigField(
            dtype=InitialPsfConfig, doc=InitialPsfConfig.__doc__)
        detection = pexConfig.ConfigField(
            dtype=measAlg.SourceDetectionTask.ConfigClass,
            doc="Initial (high-threshold) detection phase for calibration"
        )

        def setDefaults(self):
            self.detection.includeThresholdMultiplier = 10.0

        def validate(self):
            pexConfig.Config.validate(self)
            if self.doComputeApCorr and not self.doPsf:
                raise ValueError("Cannot compute aperture correction without doing PSF determination")

Example of a `RegistryField` created from a `Registry` object and use of
both the `Registry.register()` method and the `registerConfigurable`
decorator::

    psfDeterminerRegistry = pexConfig.makeRegistry("""A registry of PSF determiner factories""")

    class PcaPsfDeterminerConfig(pexConfig.Config):
        spatialOrder = pexConfig.Field(
                "spatial order for PSF kernel creation", int, 2)
        [...]

    @pexConfig.registerConfigurable("pca", psfDeterminerRegistry)
    class PcaPsfDeterminer(object):
        ConfigClass = PcaPsfDeterminerConfig
            # associate this Configurable class with its Config class for use
            # by the registry
        def __init__(self, config, schema=None):
            [...]
        def determinePsf(self, exposure, psfCandidateList, metadata=None):
            [...]

    psfDeterminerRegistry.register("shapelet", ShapeletPsfDeterminer)

    class MeasurePsfConfig(pexConfig.Config):
        psfDeterminer = measAlg.psfDeterminerRegistry.makeField("PSF determination algorithm", default="pca")


Inspecting a `Config` Object
------------------------------

Iterating through a `Config` yields the names of the `Field`\ s it contains.
The standard dictionary-like keys(), items(), iterkeys(), iteritems(), and
itervalues() methods are also supported.

Config.history contains the history of all changes to the Config's fields.
Each Field also has a history.  The formatHistory(fieldName) method displays
the history of a given Field in a more human-readable format.

help(configObject) can be used to inspect the Config's doc strings as well as
those of its Fields.

Wrapping C++ Control Objects
----------------------------

C++ control objects defined using the LSST_CONTROL_FIELD macro in
`lsst/pex/config.h` can be wrapped using SWIG and the functions in
`lsst.pex.config.wrap`, creating an equivalent Python `Config`.  The
`Config` will automatically create and set values in the C++ object, will
provide access to the doc strings from C++, and will even call the C++ class's
`validate()` method, if one exists.  This helps to minimize duplication of
code. In C++:

.. code-block:: c++

    struct FooControl {
        LSST_CONTROL_FIELD(bar, int, "documentation for field 'bar'");
        LSST_CONTROL_FIELD(baz, double, "documentation for field 'baz'");
        
        FooControl() : bar(0), baz(0.0) {}
    };

Note that only ``bool``, ``int``, ``double``, and ``std::string`` fields, along
with ``std::list`` and ``std::vector`` s of those types, are fully supported.
Nested control objects are not supported.

After using SWIG, the preferred way to create the `Config` is via the
`wrap` decorator::

    from lsst.pex.config import wrap, Config
    @wrap(FooControl)
    class FooConfig(Config):
        pass


Notes
=====

Relationship to `pex_policy`
------------------------------

The `Policy` and `PolicyDictionary` classes in the `pex_policy` package
provided many of the features of `pex_config` in C++ and, via SWIG wrapping,
Python.  `pex_config` was developed to provide additional features and remove
some shortcomings.  `pex_policy` is being replaced with `pex_config` in the
LSST DMS codebase; to aid the transition a utility function is provided to
convert a `Config` to a `Policy`.


Architecture
------------
`Config` uses a metaclass to record the `Field` attributes within each
`Config` object in an internal dictionary.  The storage and history for the
fields is also maintained in the `Config`, not the `Field` itself.  This
allows `Field`\ s to be inherited without difficulty.


See Also
========

See also :wiki:`Winter2012/ConfigTutorial`.

`Doxygen <http://lsst-web.ncsa.illinois.edu/doxygen/x_masterDoxyDoc/namespacelsst_1_1pex_1_1config.html>`_ for `pex_config`.
