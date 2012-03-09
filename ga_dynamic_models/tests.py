from ga_dynamic_models.utils import *

declare_model(simple_geomodel('MyGeoModel',
    geom = simple_geofield('PointField'),
    some_name = simple_geofield('CharField', max_length=255, default='', null=True, db_index=True),
    some_integer = simple_geofield("IntegerField", default=10)
))

declare_model(simple_model("MyRegularModel",
    some_name = simple_field('CharField', max_length=255, default='', null=True, db_index=True),
    some_integer = simple_field("IntegerField", default=10)
))

