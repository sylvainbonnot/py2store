from py2store.errors import WritesNotAllowed, DeletionsNotAllowed, OverWritesNotAllowedError
from py2store.util import lazyprop


class IdentityKeysWrapMixin:
    """Transparent KeysWrapABC. Often placed in the mro to satisfy the KeysWrapABC need in a neutral way.
    This is useful in cases where the keys the persistence functions work with are the same as those you want to work
    with.
    """

    def _id_of_key(self, k):
        """
        Maps an interface identifier (key) to an internal identifier (_id) that is actually used to perform operations.
        Can also perform validation and permission checks.
        :param k: interface identifier of some data
        :return: internal identifier _id
        """
        return k

    def _key_of_id(self, _id):
        """
        The inverse of _id_of_key. Maps an internal identifier (_id) to an interface identifier (key)
        :param _id:
        :return:
        """
        return _id


class IdentityValsWrapMixin:
    """ Transparent ValsWrapABC. Often placed in the mro to satisfy the KeysWrapABC need in a neutral way.
        This is useful in cases where the values can be persisted by __setitem__ as is (or the serialization is
        handled somewhere in the __setitem__ method.
    """

    def _data_of_obj(self, v):
        """
        Serialization of a python object.
        :param v: A python object.
        :return: The serialization of this object, in a format that can be stored by __getitem__
        """
        return v

    def _obj_of_data(self, data):
        """
        Deserialization. The inverse of _data_of_obj.
        :param data: Serialized data.
        :return: The python object corresponding to this data.
        """
        return data


class IdentityKvWrapMixin(IdentityKeysWrapMixin, IdentityValsWrapMixin):
    """Transparent Keys and Vals Wrap"""
    pass


from functools import partial

encode_as_utf8 = partial(str, encoding='utf-8')


class StringKvWrap(IdentityKvWrapMixin):
    def _obj_of_data(self, v):
        return encode_as_utf8(v)


class PrefixRelativizationMixin:
    """
    Mixin that adds a intercepts the _id_of_key an _key_of_id methods, transforming absolute keys to relative ones.
    Designed to work with string keys, where absolute and relative are relative to a _prefix attribute
    (assumed to exist).
    The cannonical use case is when keys are absolute file paths, but we want to identify data through relative paths.
    Instead of referencing files through an absolute path such as
        /A/VERY/LONG/ROOT/FOLDER/the/file/we.want
    we can instead reference the file as
        the/file/we.want

    Note though, that PrefixRelativizationMixin can be used, not only for local paths,
    but when ever a string reference is involved.
    In fact, not only strings, but any key object that has a __len__, __add__, and subscripting.

    When subclassed, should be placed before the class defining _id_of_key an _key_of_id.
    Also, assumes that a (string) _prefix attribute will be available.

    >>> from py2store.base import Store
    >>> from collections import UserDict
    >>>
    >>> class MyStore(PrefixRelativizationMixin, Store):
    ...     def __init__(self, store, _prefix='/root/of/data/'):
    ...         super().__init__(store)
    ...         self._prefix = _prefix
    ...
    >>> s = MyStore(store=dict())  # using a dict as our store
    >>> s['foo'] = 'bar'
    >>> assert s['foo'] == 'bar'
    >>> s['too'] = 'much'
    >>> assert list(s.keys()) == ['foo', 'too']
    >>> # Everything looks normal, but are the actual keys behind the hood?
    >>> s._id_of_key('foo')
    '/root/of/data/foo'
    >>> # see when iterating over s.items(), we get the interface view:
    >>> list(s.items())
    [('foo', 'bar'), ('too', 'much')]
    >>> # but if we ask the store we're actually delegating the storing to, we see what the keys actually are.
    >>> s.store.items()
    dict_items([('/root/of/data/foo', 'bar'), ('/root/of/data/too', 'much')])
    """

    @lazyprop
    def _prefix_length(self):
        return len(self._prefix)

    def _id_of_key(self, k):
        return self._prefix + k

    def _key_of_id(self, _id):
        return _id[self._prefix_length:]


class FilteredKeysMixin:
    """
    Filters __iter__ and __contains__ with (the boolean filter function attribute) _key_filt.
    """

    def __iter__(self):
        return filter(self._key_filt, super().__iter__())

    def __contains__(self, k) -> bool:
        """
        Check if collection of keys contains k.
        Note: This method iterates over all elements of the collection to check if k is present.
        Therefore it is not efficient, and in most cases should be overridden with a more efficient version.
        :return: True if k is in the collection, and False if not
        """
        return self._key_filt(k) and super().__contains__(k)


########################################################################################################################
# Mixins to disable specific operations

class ReadOnlyMixin:
    """Put this as your first parent class to disallow write/delete operations"""

    def __setitem__(self, k, v):
        raise WritesNotAllowed("You can't write with that Store")

    def __delitem__(self, k):
        raise DeletionsNotAllowed("You can't delete with that Store")

    def clear(self):
        raise DeletionsNotAllowed("You can't delete (so definitely not delete all) with that Store")

    def pop(self, k):
        raise DeletionsNotAllowed("You can't delete (including popping) with that Store")


class OverWritesNotAllowedMixin:
    """Mixin for only allowing a write to a key if they key doesn't already exist.
    Note: Should be before the persister in the MRO.

    >>> class TestPersister(OverWritesNotAllowedMixin, dict):
    ...     pass
    >>> p = TestPersister()
    >>> p['foo'] = 'bar'
    >>> #p['foo'] = 'bar2'  # will raise error
    >>> try:
    ...     p['foo'] = 'this value should not be store'
    ... except OverWritesNotAllowedError as e:
    ...     pass  # all is fine: OverWritesNotAllowedError is what we expect
    ... else:
    ...     raise RuntimeWarning("Actually, we EXPECT for an OverWritesNotAllowedError to be raised")
    """
    def __setitem__(self, k, v):
        if self.__contains__(k):
            raise OverWritesNotAllowedError(
                "key {} already exists and cannot be overwritten. "
                "If you really want to write to that key, delete it before writing".format(k))
        super().__setitem__(k, v)


########################################################################################################################
# Mixins to define mapping methods from others

class GetBasedContainerMixin:
    def __contains__(self, k) -> bool:
        """
        Check if collection of keys contains k.
        Note: This method actually fetches the contents for k, returning False if there's a key error trying to do so
        Therefore it may not be efficient, and in most cases, a method specific to the case should be used.
        :return: True if k is in the collection, and False if not
        """
        try:
            self.__getitem__(k)
            return True
        except KeyError:
            return False


class IterBasedContainerMixin:
    def __contains__(self, k) -> bool:
        """
        Check if collection of keys contains k.
        Note: This method iterates over all elements of the collection to check if k is present.
        Therefore it is not efficient, and in most cases should be overridden with a more efficient version.
        :return: True if k is in the collection, and False if not
        """
        for collection_key in self.__iter__():
            if collection_key == k:
                return True
        return False  # return False if the key wasn't found


class IterBasedSizedMixin:
    def __len__(self) -> int:
        """
        Number of elements in collection of keys.
        Note: This method iterates over all elements of the collection and counts them.
        Therefore it is not efficient, and in most cases should be overridden with a more efficient version.
        :return: The number (int) of elements in the collection of keys.
        """
        # TODO: some other means to more quickly count files?
        # Note: Found that sum(1 for _ in self.__iter__()) was slower for small, slightly faster for big inputs.
        count = 0
        for _ in self.__iter__():
            count += 1
        return count


class IterBasedSizedContainerMixin(IterBasedSizedMixin, IterBasedContainerMixin):
    """
    An ABC that defines
        (a) how to iterate over a collection of elements (keys) (__iter__)
        (b) check that a key is contained in the collection (__contains__), and
        (c) how to get the number of elements in the collection
    This is exactly what the collections.abc.Collection (from which Keys inherits) does.
    The difference here, besides the "Keys" purpose-explicit name, is that Keys offers default
     __len__ and __contains__  definitions based on what ever __iter__ the concrete class defines.

    Keys is a collection (i.e. a Sized (has __len__), Iterable (has __iter__), Container (has __contains__).
    It's purpose is to serve as a collection of object identifiers in a key->obj mapping.
    The Keys class doesn't implement __iter__ (so needs to be subclassed with a concrete class), but
    offers mixin __len__ and __contains__ methods based on a given __iter__ method.
    Note that usually __len__ and __contains__ should be overridden to more, context-dependent, efficient methods.
    """
    pass


class HashableMixin:
    def __hash__(self):
        return id(self)

    def __eq__(self, other):
        return hash(self) == hash(other)
