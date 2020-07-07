import collections.abc as cabc
import collections
import functools
import itertools
import pathlib
import reprlib

#E Directory Tree Generator
def _resolve(path, followlinks):
    return (
        (followlinks and path.is_symlink() and path.resolve().is_dir())
        or path.is_dir()
    )

def _iterdir(path, key):
    items = sorted(path.iterdir(), key=key)
    groups = {
        k: list(v)
        for k, v in itertools.groupby(items, key=key)
    }
    return groups.get(True, []), groups.get(False, [])


def walk(top, topdown=True, onerror=None, followlinks=False):
    """
    Just like os.walk, only yields a 3-tuple of
        * A pathlib object representing the current directory
        * A list of pathlib objects representing the directories
        * A list of pathlib objects representing the files
    
    See: os.walk
    """
    path = pathlib.Path(top)
    key = functools.partial(_resolve, followlinks=followlinks)
    stack = []
    _this_iter = iter([path])
    _next = collections.deque()
    while True:
        try:
            try:
                item = next(_this_iter)
            except StopIteration:
                if not _next:
                    if not topdown:
                        yield from reversed(stack)
                    return
                _this_iter = iter(_next.pop())
                continue
            dirs, files = _iterdir(item, key)
        except OSError as error:
            if onerror is not None:
                onerror(error)
            return
        if topdown:
            yield item, dirs, files
        else:
            stack.append((item, dirs, files))
        _next.appendleft(dirs)

## Vector Paths
THIS = object()
CHAIN = object()

def _chain(rtype):
    def inner(iterable):
        return rtype(itertools.chain.from_iterable(iterable))
    return inner


def _mkargv(paths, args, kwargs):
    _len = len(paths)
    positional = itertools.repeat(tuple(), _len)
    keyword = itertools.repeat(dict(), _len)
    _positional = []
    for arg in args:
        vector = itertools.repeat(arg, _len)
        if isinstance(arg, Args):
            vector = arg
        _positional.append(vector)
    if _positional:
        positional = zip(*_positional)

    _keys = [
        itertools.repeat(k, _len)
        for k in kwargs.keys()
    ]
    _values = []
    for value in kwargs.values():
        vector = itertools.repeat(value, _len)
        if isinstance(value, Args):
            vector = value
        _values.append(vector)
    _pairs = (
        zip(k, v)
        for k, v in zip(_keys, _values)
    )
    _keywords = [
        dict(p)
        for p in zip(*_pairs)
    ]
    if _keywords:
        keyword = _keywords
    return zip(paths, positional, keyword)


class Args(list):
    """
    A list.  Used for instance type checking.
    """
    pass


class _BoolVector(cabc.Sequence):
    def __repr__(self):
        return (
            f"<{type(self).__qualname__}"
            f"({reprlib.repr(self._data)})>"
        )

    def __init__(self, data, /):  # noqa: E225
        self._data = tuple(data)

    def __getitem__(self, item):
        return self._data[item]

    def __len__(self):
        return len(self._data)

    def __and__(self, other):
        if not isinstance(other, _BoolVector):
            return NotImplemented
        return _BoolVector(
            l and r
            for l, r in zip(self, other)
        )

    def __xor__(self, other):
        if not isinstance(other, _BoolVector):
            return NotImplemented
        return _BoolVector(
            (l or r) and (not (l and r))
            for l, r in zip(self, other)
        )

    def __or__(self, other):
        if not isinstance(other, _BoolVector):
            return NotImplemented
        return _BoolVector(
            l or r
            for l, r in zip(self, other)
        )

    def __invert__(self):
        return _BoolVector(not l for l in self)


class _DescriptorBase:
    __doc__ = ""
    def __init__(self, rtype=iter):
        self._rtype = rtype
        self._name = None
        self._owner = None
        self.__doc__ = ""

    def __set_name__(self, owner, name):
        self._name = name
        self._owner = owner
        self.__doc__ = getattr(pathlib.Path, self._name).__doc__


class _PathProperty(_DescriptorBase):
    def __get__(self, instance, owner=None):
        if instance is None:
            # This garbage right here is just for pydoc
            return property(fget=self.__get__, doc=self.__doc__)
        rtype = self._rtype
        if rtype is THIS:
            rtype = type(instance)
        return rtype(
            getattr(path, self._name)
            for path in instance._paths
        )


class _PathMethod(_DescriptorBase):
    def __get__(self, instance, owner=None):
        if instance is None:
            # This garbage right here is just for pydoc
            v = lambda *a, **kw: self(*a, **kw)
            v.__name__ = self._name
            v.__doc__ = self.__doc__
            return v
        part = functools.partial(self, instance)
        part.__doc__ = self.__doc__
        return part

    def __call__(self, instance, *args, chain=False, **kwargs):
        rtype = self._rtype
        if rtype is THIS:
            rtype = type(instance)
        if rtype is CHAIN:
            rtype = functools.partial(map, type(instance))
            if chain:
                rtype = _chain(type(instance))
        arguments = _mkargv(instance._paths, args, kwargs)
        return rtype(
            getattr(path, self._name)(*p, **kw)
            for path, p, kw in arguments
        )


class Paths(cabc.Sequence):
    """
    A collection object for pathlib.Path, supports the sequence API, and
    vectorized versions of all methods on pathlib.Path objects that do not
    modify the filesystem.

    This class does not implement methods that modify the filesystem, for
    safety sake.
    
    See: DangerousPaths, pathlib
    """
    @classmethod
    def from_path(cls, path):
        return cls([pathlib.Path(path)])

    def __init__(self, paths, /):  # noqa: E225
        self._paths = tuple(paths)

    def __repr__(self):
        return (
            f"<{type(self).__qualname__}"
            f"({reprlib.repr(self._paths)})>"
        )

    def __contains__(self, other):
        return other in self._paths

    def __iter__(self):
        return iter(self._paths)

    def __getitem__(self, item):
        if isinstance(item, cabc.Iterable):
            return type(self)(
                path
                for path, i in zip(self._paths, item)
                if i
            )
        if isinstance(item, slice):
            return type(self)(self._paths[item])
        return self._paths[item]

    def __len__(self):
        return len(self._paths)

    def __add__(self, other):
        if isinstance(other, Paths):
            return type(self)(self._paths + other._paths)
        return NotImplemented

    def item_replace(self, index, item):
        data = list(self._paths)
        data[index] = item
        return type(self)(data)

    def item_insert(self, index, item):
        data = list(self._paths)
        data.insert(index, item)
        return type(self)(data)

    def item_append(self, item):
        return self + type(self)([item])

    def item_remove(self, index):
        data = list(self._paths)
        del data[index]
        return type(self)(data)

    parts = _PathProperty()
    drive = _PathProperty()
    root = _PathProperty()
    anchor = _PathProperty()
    parents = _PathProperty()
    parent = _PathProperty(rtype=THIS)
    name = _PathProperty()
    suffix = _PathProperty()
    suffixes = _PathProperty()
    stem = _PathProperty()

    as_posix = _PathMethod()
    as_uri = _PathMethod()
    is_absolute = _PathMethod(rtype=_BoolVector)
    is_reserved = _PathMethod(rtype=_BoolVector)
    joinpath = _PathMethod(rtype=THIS)
    match = _PathMethod(rtype=_BoolVector)
    relative_to = _PathMethod(rtype=THIS)
    with_name = _PathMethod(rtype=THIS)
    with_suffix = _PathMethod(rtype=THIS)

    stat = _PathMethod()
    exists = _PathMethod(rtype=_BoolVector)
    expanduser = _PathMethod(rtype=THIS)
    glob = _PathMethod(rtype=CHAIN)
    group = _PathMethod()
    is_dir = _PathMethod(rtype=_BoolVector)
    is_file = _PathMethod(rtype=_BoolVector)
    is_mount = _PathMethod(rtype=_BoolVector)
    is_symlink = _PathMethod(rtype=_BoolVector)
    is_socket = _PathMethod(rtype=_BoolVector)
    is_fifo = _PathMethod(rtype=_BoolVector)
    is_block_device = _PathMethod(rtype=_BoolVector)
    is_char_device = _PathMethod(rtype=_BoolVector)
    iterdir = _PathMethod(rtype=CHAIN)
    lstat = _PathMethod()
    owner = _PathMethod()
    read_bytes = _PathMethod()
    read_text = _PathMethod()
    resolve = _PathMethod(rtype=THIS)
    rglob = _PathMethod(rtype=CHAIN)
    samefile = _PathMethod(rtype=_BoolVector)


class DangerousPaths(Paths):
    """
    Version of Paths that implement filesystem modifying methods.
    """
    chmod = _PathMethod()
    lchmod = _PathMethod()
    link_to = _PathMethod()
    mkdir = _PathMethod()
    open = _PathMethod()
    rename = _PathMethod()
    replace = _PathMethod()
    rmdir = _PathMethod()
    symlink_to = _PathMethod()
    touch = _PathMethod()
    unlink = _PathMethod()
    write_bytes = _PathMethod()
    write_text = _PathMethod()


if __name__ == '__main__':
    def errors(error):
        print(error)
    import time, os
    p = pathlib.Path(__file__).resolve().parent
    
    t1 = time.time()
    for _ in walk(p, onerror=errors): pass
    t2 = time.time()
    print(f"Mine\tdown:\t{t2 - t1} seconds")

    t1 = time.time()
    for _ in walk(p, onerror=errors, topdown=False): pass
    t2 = time.time()
    print(f"Mine\tup:\t{t2 - t1} seconds")

    t1 = time.time()
    for _ in os.walk(p, onerror=errors): pass
    t2 = time.time()
    print(f"OS\tdown:\t{t2 - t1} seconds")

    t1 = time.time()
    for _ in os.walk(p, onerror=errors, topdown=False): pass
    t2 = time.time()
    print(f"OS\tup:\t{t2 - t1} seconds")

    w = pathlib.Path(__file__).resolve()
    x = w.parent
    y = x.parent
    z = Paths([w, x, y])
    print('Repr')
    print(z)
    print()
    print("Property Access")
    print(list(z.name))
    print(z.parent)
    print()
    print("Method call")
    print(list(z.is_dir()))
    print(z.expanduser())
    print()
    print('Chain False -> True')
    print(list(z.glob('*.py')))
    print(z.glob('*.py', chain=True))
    print()
    print("Bool vector filtering")
    print(z[z.is_dir()])
    print()
    print('Single positional argument')
    print(z[
        z.samefile(w)
    ])
    print('Single keyword argument')
    print(z[
        z.samefile(other_path=w)
    ])
    print('Vector positional argument')
    print(z[
        z.samefile(
            Args([w, x, y])
        )
    ])
    print('Vector keyword argument')
    _samefile = z.samefile(
        other_path=Args([w, x, y]),
    )
    _isfile = z.is_file()
    _flags = ~(_samefile ^ _isfile)
    print(_flags)
    print(z[_flags])
