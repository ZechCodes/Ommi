"""Generate API reference pages."""
from pathlib import Path
import mkdocs_gen_files


def _scan_for_module_imports(file_path, package_name):
    imports = set()
    with open(file_path, "r") as f:
        for line in f:
            if line.startswith("import"):
                imports.update(line.split(" ", maxsplit=1)[1].split(","))
            elif line.startswith("from"):
                from_import = line.split(" ", maxsplit=2)[1]
                imports.update(f"{from_import}.{import_.strip()}" for import_ in line.split(" ", maxsplit=3)[3].split(","))

    return [
        f"{package_name}{import_.strip()}" if import_.startswith(".") else import_.strip() for import_ in imports
    ]

nav = mkdocs_gen_files.Nav()
root = Path(__file__).parent.parent
src = root / "ommi"  # Path to your source code

for path in sorted(src.rglob("*.py")):
    # Skip all files in ext/drivers except __init__.py
    module_path = path.relative_to(src).with_suffix("")
    doc_path = path.relative_to(src).with_suffix(".md")
    full_doc_path = Path("api-reference", doc_path)

    parts = tuple(module_path.parts)
    is_ext_drivers = parts[:2] == ("ext", "drivers")
    if is_ext_drivers and len(parts) > 2 and parts[2] != "__init__":
        continue

    # Skip __main__ files
    if parts and parts[-1] == "__main__":
        continue


    # Handle __init__ files
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
        if not parts:  # Skip top-level __init__.py
            continue

        if not is_ext_drivers:
            continue

        name = f"drivers.md"
        doc_path = doc_path.with_name(name)
        full_doc_path = full_doc_path.with_name(name)


    # Write mkdocstrings directive
    identifier = ".".join(parts)
    if is_ext_drivers:
        for driver_path in path.parent.iterdir():
            if driver_path.is_dir() and not driver_path.name.startswith("_"):
                driver_name = driver_path.name
                nav[parts] = doc_path.with_name(f"{driver_name}.md").as_posix()
                imports = _scan_for_module_imports(driver_path / "__init__.py", f"{identifier}.{driver_path.name}")
                with mkdocs_gen_files.open(full_doc_path.with_name(f"{driver_name}.md"), "w") as fd:
                    fd.write(
                        f"::: {identifier}.{driver_path.name}\n"
                        f"    options:\n"
                        f"      show_root_heading: false\n"
                        f"      show_root_toc_entry: false\n"
                        f"      show_source: false\n"
                        f"      show_docstring: true\n\n"
                    )
                    # for import_ in imports:
                    #     import_ = import_.strip()
                    #     if import_:
                    #         fd.write(f"::: {import_}\n")
                    #         fd.write(
                    #             f"    options:\n"
                    #             f"      show_root_heading: true\n"
                    #             f"      show_if_no_docstring: true\n"
                    #             # f"      members: true\n"
                    #             # f"      show_signature: true\n"
                    #             # f"      show_docstring: true\n"
                    #             f"      filters:\n"
                    #             f"        - '!^_'\n\n"
                    #         )
    else:
        if parts:
            nav[parts] = doc_path.as_posix()

        with mkdocs_gen_files.open(full_doc_path, "w") as fd:
            print(f"Generating API reference for {identifier}\n- {full_doc_path.name}\n- {'Added to nav' if parts else 'Not added to nav'}")
            fd.write(f"::: {identifier}")
