import _meep
import numpy as N

class Material(object):
    """
    Base class which represents a generic material. 
    """
    
    def __init__(self):
        object.__init__(self)

class Dielectric(Material):
    """
    Represents a material with a dielectric constant and optional
    polarizability resonances.
    """
    
    def __init__(self, epsilon=1.0):
        Material.__init__(self)
        self.epsilon = epsilon
        self._polarizabilities = []
    
    @property
    def epsilon(self):
        """
        Relative dielectric constant of the material.
        
        .. warning::
        
           Complex dielectric constants are not supported by Meep.
        """
        return self._epsilon
    
    @epsilon.setter
    def epsilon(self, value):
        self._epsilon = value

    @property
    def polarizabilities(self):
        """
        List of polarizability resonances.
        
        :rtype: List of tuples containing :math:`(\\sigma, \\omega, \\gamma)`
            (see :meth:`~meep.Dielectric.add_polarizability`.)
        """
        return self._polarizabilities

    def add_polarizability(self, sigma, omega, gamma):
        """
        Add a polarizability resonance to the material. This can be used to
        implement metals.
        
        Be careful to specify the parameters in the proper units. Frequencies
        should be given in Meep units, and the conductivity is specified as
        follows:
        
        .. math:: \\sigma = \\frac{f \\omega_p^2}{\\omega^2}
        
        where :math:`f` is the resonance strength, :math:`\\omega_p` is the
        plasma frequency in Meep units, and :math:`\\omega` is the resonance
        frequency in Meep units.
        
        :param sigma: conductivity (in units as above)
        :param omega: resonance frequency (in Meep frequency units)
        :param gamma: damping frequency (in Meep frequency units)
        """
        self._polarizabilities.append((sigma, omega, gamma))

# Define a material
air = Dielectric(1.0)
"""A predefined material representing ideal air or vacuum."""
vacuum = air
"""Another name for :data:`air`."""

class HasDimensions(object):
    """
    Base class for objects that can have an arbitrary number of dimensions,
    like material regions.
    
    This is designed to prevent things like a 3-D source being placed into a
    2-D computational grid. For example:
    
    .. testsetup:: *
    
       import meep
    
    .. doctest::
    
       >>> grid = meep.Geometry(size=(4, 4), resolution=50)
       >>> grid.dimensions
       2
       >>> # We can add a square region to the 2-D volume
       >>> grid.add_polygon(meep.Block(center=(0, 0), size=(2, 2)))
       >>> # Now try to add a cubical region
       >>> grid.add_polygon(meep.Block(center=(0, 0, 0), size=(2, 2, 2)))
       Traceback (most recent call last):
       ValueError: Number of dimensions in polygon must match number
       of dimensions in geometry
    
    If an object hasn't been able to figure out how many dimensions it has
    yet, then that will remain unspecified until it is able to infer that. For
    example, if you create a :class:`meep.Source` without specifying any
    coordinates, then you can specify coordinates later with any number of
    dimensions. Once you have specified coordinates, you cannot later specify
    a size with a different number of dimensions.
    """
    
    def __init__(self):
        object.__init__(self)
        self._dimensions = None  # not specified yet
    
    @property
    def dimensions(self):
        """
        Number of dimensions of the object. If the object doesn't know how
        many dimensions it has yet, then this is ``None``.
        """
        return self._dimensions
    
    @staticmethod
    def must_agree(setter):
        """
        Decorator for properties that take a coordinate tuple. The first time
        a coordinate tuple is assigned to the property, it figures out the
        number of dimensions. Subsequent coordinate tuples assigned to any
        :meth:`~meep.HasDimensions.must_agree` property must match the number
        of dimensions.
        
        For example:
        
        .. doctest::
        
            >>> class Point(meep.HasDimensions):
            ...     def __init__(self):
            ...         meep.HasDimensions.__init__(self)
            ...         self._coordinates = None
            ...     
            ...     @property
            ...     def coordinates(self):
            ...         return self._coordinates
            ...     
            ...     @coordinates.setter
            ...     @meep.HasDimensions.must_agree
            ...     def coordinates(self, value):
            ...         self._coordinates = value
            ...
            >>> point = Point()
            >>> point.dimensions is None
            True
            >>> point.coordinates = (2, 3)
            >>> point.dimensions
            2
            
        """
        def wrapper(self, value):
            num_dimensions = len(value)
            if self._dimensions is None:
                self._dimensions = num_dimensions
            elif self._dimensions != num_dimensions:
                raise ValueError('{} coordinates have wrong number of dimensions, '
                    'expected {}'.format(setter.__name__, self._dimensions))
            setter(self, value)
        return wrapper

class Geometry(HasDimensions):
    """
    This is the simulation geometry. It has a certain size and can contain
    regions of a certain material function, sources, and boundary layers.
    
    Note that the coordinates at the center of the volume are (0, 0). This is
    the same as in the Scheme interface to Meep, and opposite to what the C++
    interface does.
    """
    
    def __init__(self, size, resolution):
        HasDimensions.__init__(self)
        if len(size) == 2:
            self._instance = _meep.vol2d(size, resolution)
            self._dimensions = 2
        self._size = N.array(size)
        self._material_function_instance = None
        self._material_mode = None
        self._polygons = []
        self._sources = []
        self._boundary_regions = []

    def __del__(self):
        _meep.grid_volume_destroy(self._instance)
        if self._material_function_instance is not None:
            if self._material_mode == 'region':
                _meep.region_material_destroy(self._material_function_instance)
    
    def add_polygon(self, polygon):
        """
        Adds a region to the geometry. It is usually used to define a
        block of a certain dielectric material.
        
        .. note::
        
           Currently, the only type of region that you can add is a
           :class:`meep.Block`.
        
        :param polygon: the region to add.
        :type polygon: :class:`meep.Polygon`
        """
        if polygon.dimensions != self._dimensions:
            raise ValueError('Number of dimensions in polygon must match '
                'number of dimensions in geometry')
        
        if self._material_function_instance is None:
            self._material_function_instance = _meep.region_material_new()
            self._material_mode = 'region'
        
        if self._material_mode != 'region':
            raise TypeError('Cannot add a polygon to a Geometry where '
                'you have already defined the material function in a '
                'different way')
        
        region_index = _meep.region_material_add_region(
            self._material_function_instance,
            polygon.center - polygon.size / 2.0,
            polygon.center + polygon.size / 2.0)
        _meep.region_material_set_region_epsilon(
            self._material_function_instance,
            region_index,
            polygon.material.epsilon)
        for sigma, omega, gamma in polygon.material.polarizabilities:
        	_meep.region_material_add_region_polarizability(
        		self._material_function_instance,
        		region_index,
        		sigma, omega, gamma)
        
        self._polygons.append(polygon)
    
    def add_source(self, source):
        """
        Adds a source to the geometry.
        
        .. note::
        
           Currently, the only type of source that you can add is a
           :class:`meep.ContinuousSource`.
        
        :param source: the source to add.
        :type source: :class:`meep.Source`
        """
        if source.dimensions != self._dimensions:
            raise ValueError('Number of dimensions in source must match '
                'number of dimensions in geometry')
        self._sources.append(source)
    
    def add_pml(self, pml):
        """
        Adds a :abbr:`PML (perfectly matched layer)` to the geometry.
        
        :param pml: the PML to add.
        :type pml: :class:`meep.PML`
        """
        self._boundary_regions.append(pml)
    
    @property
    def size(self):
        """
        The size of the geometry. This is the computational volume of the
        simulation.
        
        :rtype: one-dimensional :class:`numpy.ndarray` with length equal to
           the number of dimensions.
        """
        return self._size


class Polygon(HasDimensions):
    
    def __init__(self):
        HasDimensions.__init__(self)


class Block(Polygon):
    
    def __init__(self, center=None, size=None, material=air):
        Polygon.__init__(self)
        if center is not None:
            self.center = center
        if size is not None:
            self.size = size
        self.material = material
    
    @property
    def center(self):
        return self._center
    
    @center.setter
    @HasDimensions.must_agree
    def center(self, value):
        self._center = N.array(value)
    
    @property
    def size(self):
        return self._size
    
    @size.setter
    @HasDimensions.must_agree
    def size(self, value):
        self._size = N.array(value)
    
    @property
    def material(self):
        return self._material
    
    @material.setter
    def material(self, value):
        if isinstance(value, Material):
            self._material = value
        else:
            try:
                epsilon = float(value)
            except TypeError:
                raise ValueError('material must be a meep.Material or a value '
                    'for epsilon')
            self._material = Dielectric(epsilon)


class Source(HasDimensions):
    
    def __init__(self, component='ex', size=None, center=None, amplitude=1.0):
        HasDimensions.__init__(self)
        self.component = component
        self.size = size
        self.center = center
        self.amplitude = amplitude
    
    def __del__(self):
        # object.__del__(self)
        pass
        
    @property
    def component(self):
        return self._component
    
    @component.setter
    def component(self, value):
        if value.lower() not in ['ex', 'ey', 'ez']:
            raise ValueError('Component type unknown')
        self._component = value.lower()
    
    @property
    def size(self):
        return self._size
    
    @size.setter
    @HasDimensions.must_agree
    def size(self, value):
        self._size = N.array(value)
    
    def is_point_source(self):
        return (self.size == 0.0).all()
    
    @property
    def center(self):
        return self._center
    
    @center.setter
    @HasDimensions.must_agree
    def center(self, value):
        self._center = N.array(value)

class ContinuousSource(Source):
    
    def __init__(self, wavelength=None, frequency=None, component='ex',
        size=None, center=None):
        Source.__init__(self, component, size, center)
        
        if wavelength is not None and frequency is not None:
            raise ValueError('Specify one of wavelength or frequency, but '
                'not both.')
        if wavelength is not None:
            frequency = 1.0 / wavelength
        if frequency is None:
            raise ValueError('frequency must be specified')
        
        self._instance = _meep.continuous_src_time_new(frequency)
        
    def __del__(self):
        Source.__del__(self)
        _meep.continuous_src_time_destroy(self._instance)
    
    @property
    def frequency(self):
        return _meep.continuous_src_time_get_frequency(self._instance)
    
    @frequency.setter
    def frequency(self, value):
        _meep.continuous_src_time_set_frequency(self._instance, value)
    
    
class PML(object):
    
    def __init__(self, thickness):
        object.__init__(self)
        self._instance = _meep.pml(thickness)
    
    def __del__(self):
        #object.__del__(self)
        _meep.boundary_region_destroy(self._instance)


class Simulation(object):
    
    def __init__(self, geometry):
        object.__init__(self)
        self.geometry = geometry
        
        self._structure_instance = _meep.structure_new(
            geometry._instance,
            geometry._material_function_instance,
            geometry._boundary_regions);
        for region in geometry._polygons:
            for sigma, omega, gamma in region.material.polarizabilities:
                _meep.structure_add_polarizability(self._structure_instance,
                    geometry._material_function_instance, omega, gamma)

        self._fields_instance = _meep.fields_new(self._structure_instance);
        
        self.epsilon = Quantity('epsilon', self)
        self.efield = Quantity('efield', self)
        
        for source in geometry._sources:
            if source.is_point_source():
                _meep.fields_add_point_source(self._fields_instance,
                    source.component,
                    source._instance,
                    source.center,
                    source.amplitude)
            else:
                _meep.fields_add_volume_source(self._fields_instance,
                    source.component,
                    source._instance,
                    source.center - source.size / 2.0,
                    source.center + source.size / 2.0,
                    source.amplitude)
    
    def __del__(self):
        #object.__del__(self)
        _meep.structure_destroy(self._structure_instance)
        _meep.fields_destroy(self._fields_instance)
    
    def step(self):
        _meep.fields_step(self._fields_instance)
    
    @property
    def time(self):
        return _meep.fields_time(self._fields_instance)


class Quantity(HasDimensions):
    
    def __init__(self, component, simulation, complex=None):
        HasDimensions.__init__(self)
        self._dimensions = simulation.geometry.dimensions
        self.component = component
        self._fields_instance = simulation._fields_instance
        self._grid_volume_instance = simulation.geometry._instance
    
    def __array__(self):
        # return a ... x 3 array for all field components
        if self.component == 'efield':
            ex = _meep.fields_get_ndarray(self._fields_instance,
                self._grid_volume_instance, 'ex')
            ey = _meep.fields_get_ndarray(self._fields_instance,
                self._grid_volume_instance, 'ey')
            ez = _meep.fields_get_ndarray(self._fields_instance,
                self._grid_volume_instance, 'ez')
            # stack on the last axis
            return N.concatenate((
                ex[..., N.newaxis], 
                ey[..., N.newaxis],
                ez[..., N.newaxis]), axis=ex.ndim)
        
        # return an array
        return _meep.fields_get_ndarray(self._fields_instance,
            self._grid_volume_instance,
            self.component)
    
    @property
    def component(self):
        return self._component
    
    @component.setter
    def component(self, value):
        if value.lower() not in ['epsilon', 'dielectric', 'efield', 'ex',
            'ey', 'ez']:
            raise ValueError('Unknown component type: {}'.format(value))
        
        # Synonyms
        if value.lower() == 'dielectric':
            value = 'epsilon'
        
        self._component = value.lower()
    
    def output_hdf5(self):
        _meep.meep_fields_output_hdf5(self._fields_instance,
            self.component,
            self._grid_volume_instance)
