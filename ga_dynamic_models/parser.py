"""
This is not terribly well documented, but the Parser transforms a dictionary contained in the database into a Model or
Resource class.  It may call methods, import modules, and do all kinds of hocus-pocus to do its job, so when letting
users declare models on their own, make sure you do so in a secure way and validate that models are actual real models.

This can be generalized to a class declaration, so long as the class declaration is done in the Django ORM style.  Thus
you could also use this to declare models in MongoEngine or a similar ORM.  YOu cannot define new methods, but you can
define class attributes all you want.  For more on how to do this, see :py:mod:`ga_dynamic_models.utils`.
"""

import importlib
import ga_ows.utils

class Parser(object):
    def __init__(self, module_name, result_metaclass=type):
        self._imports = {}
        self._result_metaclass = result_metaclass
        self._module_name = module_name

    def _ensure_import(self, module):
        if module not in self._imports:
            self._imports[module] = importlib.import_module(module)
        return self._imports[module]

    def _parse_item(self, item):
        ret = item
        if isinstance(item, dict):
            t = item['type']
            if t == 'callable':
                ret = self._parse_callable(**item)
            elif t == 'attribute':
                ret = self._parse_attribute(**item)
            elif t == 'class_attribute':
                ret = self._parse_class_attribute(**item)
            elif t == 'class_method':
                ret = self._parse_class_method(**item)
            elif t == 'attribs':
                ret = self._parse_attribs(**item)
            elif t == 'queryset':
                ret = self._parse_queryset(**item)
            elif t == 'datetime':
                ret = ga_ows.utils.parsetime(item['value'])
        else:
            try:
                ret = int(item) # correct for the fact that JSON doesn't differentiate between ints and floats
            except ValueError:
                pass
        return ret
    
    def _parse_positionals(self, parameters):
        if 'positionals' in parameters:
            return [self._parse_item(it) for it in parameters['positionals']]
        else:
            return []
    
    def _parse_keywords(self, parameters):
        if 'keywords' in parameters:
            return dict([(key, self._parse_item(value)) for key, value in parameters['keywords'].items()])
        else:
            return {}
    
    def _parse_bases(self, bases):
        return tuple([self._parse_attribute(**base) for base in bases])

    def _parse_attribs(self, type, module, ls):
        print type, module, ls

        m = self._ensure_import(module)
        if isinstance(ls, str) or isinstance(ls, unicode):
            return m.__getattribute__(ls)

        attr = m.__getattribute__(ls[0])
        for it in ls[1:]:
            if isinstance(it, str) or isinstance(it, unicode):
                it = it.encode('ascii')
                attr = attr.__getattribute__(it)
            else:
                attr = attr(*self._parse_positionals(it), **self._parse_keywords(it))
        return attr

    def _parse_queryset(self, type, module, model, extra):
        module = self._ensure_import(module)
        q = module.__getattribute__(model).objects
        for method in extra:
            q = q.__getattribute__(method['method'])(*self._parse_positionals(method['parameters'], **self._parse_keywords(method['parameters'])))
        return q

    def _parse_callable(self, type, module, callable, parameters):
        m= self._ensure_import(module)
        return m.__getattribute__(callable)(*self._parse_positionals(parameters), **self._parse_keywords(parameters))
    
    def _parse_attribute(self, type, module, attribute):
        m=self._ensure_import(module)
        return m.__getattribute__(attribute)
    
    def _parse_class_attribute(self, type, module, cls, attribute):
        m=self._ensure_import(module)
        c = m.__getattribute__(cls)
        return c.__getattribute__(attribute)
    
    def _parse_class_method(self, type, module, cls, method, parameters):
        m=self._ensure_import(module)
        m.__getattribute__(cls).__getattribute__(method)(*self._parse_positionals(parameters), **self._parse_keywords(parameters))
    
    def _parse_meta(self, **kwds):
        return type("Meta", (object,), dict([(k, self._parse_item(v)) for k, v in kwds.items()]))
    
    def parse(self, name, bases, fields, meta, **kwargs):
        name = name.encode('ascii')
        fs =  dict([(n.encode('ascii'), self._parse_callable(**f)) for n, f in fields.items()])
        fs['Meta'] = self._parse_meta(**meta)
        fs['__metaclass__'] = self._result_metaclass
        fs['__module__'] = self._module_name
    
        t = type(name, self._parse_bases(bases), fs)
        for k, v in kwargs.items():
            if not k.startswith('_'):
                t.__setattr__(k, self._parse_item(v))
            return t