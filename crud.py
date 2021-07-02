import json

def get_args(request):
    d = {}

    args = {}
    if request.body:
        args = json.loads(request.body)

    for k, v in args.items():
        d[k] = v

    for k, v in request.GET.items():
        d[k] = v

    print('GETARGS: ', d)

    return d
        

from django.http import JsonResponse, Http404
from django.db import transaction
from django.urls import path
from django.conf.urls import include
import django.db.models.fields.related


from glib2.journal.models import Journalable
from glib2.api_access.helpers import login_required
from django.forms.models import model_to_dict
from django.db.models.fields.reverse_related import ManyToOneRel
from django.db.models import AutoField

def model_to_dict_more(path, obj, *extra_fields):
    f = obj._meta.model._meta.get_fields(include_parents=True, include_hidden=True)

    d = model_to_dict(obj)

    for i in f:
        if i.name not in d:
            if type(i) == ManyToOneRel:
                continue
            d[i.name] = i.value_from_object(obj)
    
    for i in extra_fields:
        if i not in d:
            d[i] = getattr(obj, i)
    d['__path__'] = '/'.join(path)
    return d


def create_easy_mode_for(model, arg_name, **kwargs):
    class EasyMode:
        non_pk_fields = []
        for i in model._meta.get_fields(include_parents=True, include_hidden=True):
            if model._meta.pk != i:
                if isinstance(i, django.db.models.fields.related.ForeignKey):                
                    non_pk_fields.append(i.attname)
                else:
                    non_pk_fields.append(i.name)                    
        
        allowed_create = set(non_pk_fields)
        allowed_update = set(non_pk_fields)

        ################################

        @classmethod
        def can_read(cls, request, **kwargs): return True

        @classmethod
        def can_update(cls, request, **kwargs): return True

        @classmethod
        def can_create(cls, request, **kwargs): return True

        @classmethod
        def can_delete(cls, request, **kwargs): return True

        @classmethod
        def can_list(cls, request, **kwargs): return True

        @classmethod
        def can_search(cls, request, **kwargs): return True

        ################################

        @classmethod
        def filter(cls, request, **kwargs):
            return dict(kwargs)

        @classmethod
        def walk(cls, request, **kwargs):
            return kwargs

        @classmethod
        def read(cls, request, **kwargs):
            fresh = cls.filter(request, **kwargs)
            fresh.pop(arg_name)
            fresh['pk'] = kwargs.get(arg_name)
            return model.objects.filter(
                **fresh,
            ).first()

        @classmethod
        def list(cls, request, **kwargs):
            return model.objects.filter(**cls.filter(request, **kwargs))

        @classmethod
        def create(cls, request, **kwargs):
            return model(**cls.filter(request, **kwargs))

        @classmethod
        def update(cls, request, **kwargs):
            fresh = cls.filter(request, **kwargs)
            fresh.pop(arg_name)
            fresh['pk'] = kwargs.get(arg_name)
            return model.objects.filter(
                **fresh,
            ).first()

    return EasyMode


def glib_crud_map_easymode(model, arg_name, **kwargs):
    em = create_easy_mode_for(model, arg_name, **kwargs)
    return glib_crud_map(model, arg_name, em)

def generate_callbacks(model, arg_name, crud_obj):
    more_fields = getattr(crud_obj, 'more_fields', [])
    
    def sets_to_dict(r, m, recurse, path, kwargs, sub_type):
        if path is None:
            path = []

        path.append(r._meta.model_name)
        path.append(str(r.pk))
        
        base = model_to_dict_more(path, r)
        foreign_set_keys = [i.name for i in m._meta.related_objects]

        for name in foreign_set_keys:
            fresh = dict(kwargs)
            fresh['fresh'] = 1
            target_set = getattr(r, name + '_set')

            if recurse is False:
                l = []

                if issubclass(target_set.model, Journalable):
                    field_name = target_set.field.attname
                    field_value = r.id
                    fresh[field_name] = field_value
                    p, max_id = target_set.model.bounded_query(**fresh)
                    for j in p:
                        l.append(model_to_dict_more(path, j))
                    base[name + '_journal'] = {
                        'rows':l,
                        'max_item_rev': max_id
                    }
                else:
                    if target_set.model == m:
                        pass
                    else:
                        for j in target_set.all():
                            l.append(model_to_dict_more(path, j))
                        if sub_type == 'set':
                            base[name + '_set'] = l
                        elif sub_type == 'map':
                            base[name + '_map'] = { i.get("uuid") or i.get('id'): i for i in l }

            if recurse is True:                
                l = []

                if issubclass(target_set.model, Journalable):
                    field_name = target_set.field.attname
                    field_value = r.id
                    fresh[field_name] = field_value
                    p, max_id = target_set.model.bounded_query(**fresh)
                    for j in p:
                        l.append(
                            sets_to_dict(j, j._meta.model, recurse, list(path), fresh, sub_type))
                    base[name + '_journal'] = {
                        'rows':l,
                        'max_item_rev': max_id
                    }
                else:
                    if target_set.model == m:
                        pass
                    else:
                        for j in target_set.all():
                            l.append(
                                sets_to_dict(j, j._meta.model, recurse, list(path), fresh, sub_type))
                        if sub_type == 'set':
                            base[name + '_set'] = l
                        elif sub_type == 'map':
                            base[name + '_map'] = { i.get('id'): i for i in l }

        return base        


    def crud_list_detail(request, **kwargs):
        body = get_args(request)
        result = crud_obj.list(request, **kwargs)
        result = result.filter(**{k:v for k, v in body.items() if not k.startswith('_')})

        return ({
            'rows': [sets_to_dict(row, model, True, None, kwargs, 'set')
                     for row in result],
        })

    def crud_list(request, **kwargs):
        body = get_args(request)
        result = crud_obj.list(request, **kwargs)
        result = result.filter(**body)
        
        return ({
            'rows': [model_to_dict_more([], i, *more_fields)
                     for i in result],
        })

    def crud_walk(request, **kwargs):
        body = get_args(request)
        bound_args = crud_obj.walk(request, **kwargs)
        items, max_safe_rev = model.bounded_query(
            last_id=int(body.get('last_id', 0)),
            fresh=body.get('fresh', '1') == '1',
            **bound_args,
        )

        return ({
            'bound_args': bound_args,
            'rows': [model_to_dict_more([], i, *more_fields) for i in items],
            'max_item_rev': max_safe_rev,
        })
        
    def crud_read(request, **kwargs):
        row = crud_obj.read(request, **kwargs)

        if row is None:
            raise Http404()            
        
        return ({'row': model_to_dict_more([], row, *more_fields)})

    def crud_clone(request, **kwargs):
        row = crud_obj.read(request, **kwargs)

        if row is None:
            raise Http404()

        row.pk = None
        row.save()
        row.refresh_from_db()
        
        return ({'row': model_to_dict_more([], row, *more_fields)})

    def crud_create(request, **kwargs):
        row = crud_obj.create(request, **kwargs)

        if row is None:
            raise Http404()
            
        body = get_args(request)
        for k, v in body.items():
            if k in crud_obj.allowed_create:
                setattr(row, k, v)

        row.save()
        row.refresh_from_db()

        return ({
            'row': model_to_dict_more([], row, *more_fields),
        })

    def crud_delete(request, **kwargs):
        row = crud_obj.update(request, **kwargs)

        if row is None:
            raise Http404()

        row.delete()

        return ({
            'row': model_to_dict_more([], row, *more_fields),
        })

    def crud_update(request, **kwargs):
        row = crud_obj.update(request, **kwargs)

        if row is None:
            raise Http404()

        body = get_args(request)

        for k, v in body.items():
            if k in crud_obj.allowed_update:
                setattr(row, k, v)

        row.save()
        row.refresh_from_db()

        return ({
            'row': model_to_dict_more([], row, *more_fields),
        })

    def crud_batch_update(request, **kwargs):
        body = get_args(request)

        rows = body.get('rows')

        results = {}

        with transaction.atomic():
            for fields in rows:
                kw = dict(kwargs)
                kw[arg_name] = fields.get('pk')
                row = crud_obj.update(request, **kw)

                if row is None:
                    continue

                for k, v in fields.items():
                    if k in crud_obj.allowed_update:
                        setattr(row, k, v)

                row.save()
                row.refresh_from_db()

                results[row.id] = row

        return ({
            'rows': {
                v.id: model_to_dict_more([], v, *more_fields)
                for k, v in results.items()
            }
        })
    

    def crud_detail(request, **kwargs):
        row = crud_obj.read(request, **kwargs)

        if row is None:
            raise Http404()

        base = sets_to_dict(row, model, True, None, kwargs, 'set')

        return ({
            'row': base,
        })

    def crud_map(request, **kwargs):
        row = crud_obj.read(request, **kwargs)

        if row is None:
            raise Http404()

        base = sets_to_dict(row, model, True, None, kwargs, 'map')

        return ({
            'row': base,
        })
    
    def crud_children(request, **kwargs):
        row = crud_obj.read(request, **kwargs)

        if row is None:
            raise Http404()

        base = sets_to_dict(row, model, False, None, kwargs, 'set')

        return ({
            'row': base,
        })

    def crud_related(request, **kwargs):
        row = crud_obj.read(request, **kwargs)

        if row is None:
            raise Http404()

        base = sets_to_dict(row, model, False, None, kwargs, 'set')

        for f in row._meta.fields:
            if isinstance(f, django.db.models.fields.related.ForeignKey):
                subrow = getattr(row, f.name)
                if subrow:
                    base[f.name] = model_to_dict_more([], subrow)
                else:
                    base[f.name] = None

        return ({
            'row': base,
        })

    def crud_reflect(request, **kwargs):
        row = crud_obj.read(request, **kwargs)

        if row is None:
            raise Http404()

        types = []

        for t in model._meta.get_fields(include_parents=True, include_hidden=True):
            if type(t) == ManyToOneRel:
                continue
            
            types.append({
                'name':t.name,
                'type':t.get_internal_type(),
            })
        
        return ({
            'row': model_to_dict_more([], row, *more_fields),
            'types': types,
        })
        

    def crud_ts_reflect(request, **kwargs):
        pass

    return locals()

def glib_crud_map(model, arg_name, crud_obj):
    callbacks = generate_callbacks(model, arg_name, crud_obj)

    capture_type = 'int'

    def wrap(cb):
        def cbw(*args, **kwargs):
            return JsonResponse(cb(*args, **kwargs))
        
        return login_required(cbw)

    urls = [
        path('list',
             wrap(callbacks['crud_list']),
             name='list'),

        path('list_detail',
             wrap(callbacks['crud_list_detail']),
             name='list_detail'),

        path('create',
             wrap(callbacks['crud_create']),
             name='create'),

        path('batch_update',
             wrap(callbacks['crud_batch_update']),
             name='batch_update'),
        
        path('<{}:{}>'.format(capture_type, arg_name),
             wrap(callbacks['crud_read']),
             name='read'),

        path('<{}:{}>/clone'.format(capture_type, arg_name),
             wrap(callbacks['crud_clone']),
             name='clone'),

        path('<{}:{}>/delete'.format(capture_type, arg_name),
             wrap(callbacks['crud_delete']),
             name='delete'),

        path('<{}:{}>/update'.format(capture_type, arg_name),
             wrap(callbacks['crud_update']),
             name='update'),

        path('<{}:{}>/detail'.format(capture_type, arg_name),
             wrap(callbacks['crud_detail']),
             name='detail'),

        path('<{}:{}>/map'.format(capture_type, arg_name),
             wrap(callbacks['crud_map']),
             name='map'),

        path('<{}:{}>/reflect'.format(capture_type, arg_name),
             wrap(callbacks['crud_reflect']),
             name='reflect'),

        path('<{}:{}>/children'.format(capture_type, arg_name),
             wrap(callbacks['crud_children']),
             name='children'),
        
        path('<{}:{}>/related'.format(capture_type, arg_name),
             wrap(callbacks['crud_related']),
             name='related'),
    ]

    if issubclass(model, Journalable):
        urls.append(
            path('walk', crud_walk, name='walk'),
        )

    return include(urls)
