import collections.abc as cabc
import functools
import itertools
import pathlib
import reprlib

THIS = object()
CHAIN = object()


def _chain(rtype):
    def inner(iterable):
        return rtype(itertools.chain.from_iterable(iterable))
    return inner

def _isiterable(obj):
    return (
        isinstance(obj, cabc.Iterable)
        and not isinstance(obj, (str, bytes, bytearray))
    )

def _isargskwargs(obj):
    return (
        len(obj) == 2
        and isinstance(obj[0], cabc.Iterable)
        and isinstance(obj[1], cabc.Mapping)
    )

class PathArg:
    """
    Iffn this is gonna break, its gonna break here
    """
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def __iter__(self):
        return iter((self.args, self.kwargs))

    @classmethod
    def from_arguments(cls, obj):
        if isinstance(obj, cabc.Mapping):
            return cls(**obj)
        if _isiterable(obj):
            if _isargskwargs(obj):
                return cls(*obj[0], **obj[1])
            return cls(*obj)
        return cls(obj)

    @classmethod
    def stream(cls, iterable):
        for item in iterable:
            yield cls.from_arguments(item)


class DescriptorBase:
    def __init__(self, rtype=iter):
        self._rtype = rtype
        self._name = None
        self._owner = None

    def __set_name__(self, owner, name):
        self._name = name
        self._owner = owner

class PathProperty(DescriptorBase):
    def __get__(self, instance, owner=None):
        rtype = self._rtype
        if rtype is THIS:
            rtype = instance.__class__
        return rtype(
            getattr(path, self._name)
            for path in instance._paths
        )


class PathMethod(DescriptorBase):
    def __get__(self, instance, owner=None):
        return functools.partial(self, instance)

    def __call__(self, instance, *args, chain=False, **kwargs):
        rtype = self._rtype
        if rtype is THIS:
            rtype = instance.__class__
        if rtype is CHAIN: 
            rtype = iter
            if chain:
                rtype = _chain(instance.__class__)
        vector = None
        if len(args) == 1 and _isiterable(args[0]):
            vector = args[0]
        if vector is None:
            vector = itertools.repeat((args, kwargs))
        vector = PathArg.stream(vector)
        return rtype(
            getattr(path, self._name)(*ar, **kw)
            for path, (ar, kw) in zip(instance._paths, vector)
        )


class Paths(cabc.Sequence):
    @classmethod
    def from_path(cls, path):
        return cls([pathlib.Path(path)])

    def __init__(self, paths):
        self._paths = tuple(paths)

    def __repr__(self):
        return (
            f"<{self.__class__.__qualname__}"
            f"(paths={reprlib.repr(self._paths)})>"
        )

    def __getitem__(self, item):
        if isinstance(item, cabc.Iterable):
            return [
                path
                for path, i in zip(self._paths, item)
                if i
            ]
        if isinstance(item, slice):
            return self.__class__(self._paths[item])
        return self._paths[item]

    def __len__(self):
        return len(self._paths)

    def __add__(self, other):
        if isinstance(other, Paths):
            return self.__class__(self._paths + other._paths)
        return NotImplemented
    
    def item_replace(self, index, item):
        data = list(self._paths)
        data[index] = item
        return self.__class__(data)

    def item_insert(self, index, item):
        data = list(self._paths)
        data.insert(index, item)
        return self.__class__(data)

    def item_append(self, item):
        return self + self.__class__([item])

    def item_remove(self, index):
        data = list(self._paths)
        del data[index]
        return self.__class__(data)

    parts = PathProperty()
    drive = PathProperty()
    root = PathProperty()
    anchor = PathProperty()
    parent = PathProperty(rtype=THIS)
    name = PathProperty()
    suffix = PathProperty()
    suffixes = PathProperty()
    stem = PathProperty()

    as_posix = PathMethod()
    as_uri = PathMethod()
    is_absolute = PathMethod()
    is_reserved = PathMethod()
    joinpath = PathMethod(rtype=THIS)
    match = PathMethod()
    relative_to = PathMethod(rtype=THIS)
    with_name = PathMethod(rtype=THIS)
    with_suffix = PathMethod(rtype=THIS)

    stat = PathMethod()
    exists = PathMethod()
    expanduser = PathMethod(rtype=THIS)
    glob = PathMethod(rtype=CHAIN)
    group = PathMethod()
    is_dir = PathMethod()
    is_file = PathMethod()
    is_mount = PathMethod()
    is_symlink = PathMethod()
    is_socket = PathMethod()
    is_fifo = PathMethod()
    is_block_device = PathMethod()
    is_char_device = PathMethod()
    iterdir = PathMethod(rtype=CHAIN)
    lstat = PathMethod()
    owner = PathMethod()
    read_bytes = PathMethod()
    read_text = PathMethod()
    resolve = PathMethod(rtype=THIS)
    rglob = PathMethod(rtype=CHAIN)
    samefile = PathMethod()


class DangerousPaths(Paths):
    chmod = PathMethod()
    lchmod = PathMethod()
    link_to = PathMethod()
    mkdir = PathMethod()
    open = PathMethod()
    rename = PathMethod()
    replace = PathMethod()
    rmdir = PathMethod()
    symlink_to = PathMethod()
    touch = PathMethod()
    unlink = PathMethod()
    write_bytes = PathMethod()
    write_text = PathMethod()

if __name__ == '__main__':
    fake = pathlib.Path(r'C:\Windows\py.exe')
    w = pathlib.Path(__file__).resolve()
    x = pathlib.Path.cwd()
    y = x.parent
    z = Paths([w, x, y])
    print(z)
    print(list(z.name))
    print(list(z.glob('*.py')))
    print(list(z.glob('*.py', chain=True)))
    print(z[z.is_dir()])
    print(z[z.samefile([fake, w, w])])
    print(z[z.samefile([w, (x,), {'other_path': y}])])
    print(z[
        z.samefile([
            ((w,), {}),
            ((x,), {}),
            ((), {'other_path': y}),
        ])
    ])
    print(z[z.samefile(w)])