import argparse
import contextlib
import sys
import types
import typing

parser = argparse.ArgumentParser()
parser.add_argument("-o", "--output")
parser.add_argument("file")

def make_string_literal(b: bytes) -> str:
    res = ['"']
    if b.isascii() and b.decode("ascii").isprintable():
        res.append(b.decode("ascii"))
    else:
        for i in b:
            res.append(f"\\x{i:02x}")
    res.append('"')
    return "".join(res)

class Printer:

    def __init__(self, file: typing.TextIO):
        self.level = 0
        self.file = file
        self.write("#include <Python.h>")
        self.write("")

    @contextlib.contextmanager
    def indent(self) -> None:
        save_level = self.level
        try:
            self.level += 1
            yield
        finally:
            self.level = save_level

    def write(self, arg: str) -> None:
        self.file.writelines(("    "*self.level, arg, "\n"))

    @contextlib.contextmanager
    def block(self, prefix: str, suffix: str = "") -> None:
        self.write(prefix + " {")
        with self.indent():
            yield
        self.write("}" + suffix)

    def object_head(self, typename: str) -> None:
        with self.block(".ob_base =", ","):
            self.write(f".ob_refcnt = 999999999,")
            self.write(f".ob_type = &{typename},")

    def object_var_head(self, typename: str, size: int) -> None:
        with self.block(".ob_base =", ","):
            self.object_head(typename)
            self.write(f".ob_size = {size},")

    def field(self, obj: object, name: str) -> None:
        self.write(f".{name} = {getattr(obj, name)},")

    def generate_bytes(self, name: str, b: bytes) -> None:
        self.write("static")
        with self.indent():
            with self.block(f"struct"):
                self.write("PyObject_VAR_HEAD")
                self.write("Py_hash_t ob_shash;")
                self.write(f"char ob_sval[{len(b) + 1}];")
        with self.block(f"{name} =", ";"):
            self.object_var_head("PyBytes_Type", len(b) + 1)
            self.write(".ob_shash = -1,")
            self.write(f".ob_sval = {make_string_literal(b)},")

    def generate_unicode(self, name: str, s: str) -> None:
        b = s.encode("utf8", errors="surrogatepass")
        assert len(s) == len(b)  # Can't handle non-ASCII names yet
        with self.block(f"static PyUnicodeObject {name} =", ";"):
            # PyCompactUnicodeObject
            with self.block("._base =", ","):
                # PyASCIIObject
                with self.block("._base =", ","):
                    self.object_head("PyUnicode_Type")
                    self.write(f".length = {len(s)},")
                    self.write(".hash = -1,")
                    # state
                    with self.block(".state =", ","):
                        self.write(".kind = 1,")  # 8 bit chars
                        self.write(".compact = 1,")  # ASCII
                        self.write(".ready = 1,")
                self.write(f".utf8_length = {len(b)},")
                self.write(f".utf8 = {make_string_literal(b)},")
                self.write(f".wstr_length = {len(s)},")

    def generate_code(self, name: str, code: types.CodeType) -> None:
        self.generate_bytes(name + "_code", code.co_code)
        self.generate_unicode(name + "_name", code.co_name)
        with self.block(f"struct PyCodeObject {name} =", ";"):
            self.object_head("PyCode_Type")
            self.field(code, "co_flags")
            self.field(code, "co_argcount")
            self.field(code, "co_posonlyargcount")
            self.field(code, "co_kwonlyargcount")
            self.field(code, "co_stacksize")
            self.field(code, "co_firstlineno")
            self.write(f".co_code = (PyObject *) &{name + '_code'},")
            self.write(f".co_name = (PyObject *) &{name + '_name'},")

def generate(filename: str, file: typing.TextIO) -> None:
    with open(filename) as f:
        source = f.read()
    code = compile(source, filename, "exec")
    printer = Printer(file)
    printer.generate_code("toplevel", code)

def main() -> None:
    args = parser.parse_args()
    closeit = False
    if args.output:
        file = open(args.output, "w")
        closeit = True
    else:
        file = sys.stdout
    try:
        generate(args.file, file)
    finally:
        if closeit:
            file.close()

main()
