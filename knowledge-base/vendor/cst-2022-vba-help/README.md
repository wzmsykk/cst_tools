# CST Studio Suite 2022 VBA offline help

This directory is a local, version-pinned knowledge-base copy of the VBA help
installed with CST Studio Suite 2022. It is retained so that CST automation
code can be reviewed against the exact API documentation used by this project.

## Source

- Product: CST Studio Suite 2022
- Local installation: `D:\Program Files (x86)\CST Studio Suite 2022\Online Help`
- Copied on: 2026-09-16
- Vendor files copied: 793
- Vendor payload size at copy time: 18,312,428 bytes

Copied trees:

- `vba/`: VBA macro-language overview and its images
- `VBA_3D/`: CST 3D project VBA object/API reference and local search index
- `chm/`: WinWrap Basic v9 compiled language help used by CST's `WWB-COM`
  macro environment

These files are vendor documentation. Keep them for local/internal reference
and do not redistribute them independently of the applicable CST licence.

## Entry points

- Macro overview: `vba/vba_macro_language_overview.htm`
- 3D VBA reference: `VBA_3D/index.htm`
- Application/project methods: `VBA_3D/common_vbaapp/common_vbaappapplication_object.htm`
- WinWrap Basic v9 help: `chm/wb9ent.chm`, `chm/wwb9_000.chm`, and
  `chm/wwb9_v90.chm`

Open the HTML files locally in a browser. The copied directory structure is
preserved so relative links and images continue to work.

Open the CHM files with Windows HTML Help. The three WinWrap Basic v9 files
were installed together under CST's `AMD64` directory and are retained
together because CST may address individual context-help files directly. Do
not rename them.

Conceptually, this knowledge base has two complementary layers:

- WinWrap Basic v9 documents the Basic language and `WWB-COM` macro runtime.
- `VBA_3D` documents CST-specific objects, methods, and solver APIs exposed to
  that runtime.

## Quit and saving semantics

The Application Object reference documents `Quit` as:

> Closes the program without saving unless the structure of the project has
> been changed.

No separate `QuitWithoutSave` method or Boolean argument to `Quit` is
documented in this CST 2022 VBA reference.

The repository history shows the following worker shutdown sequence:

- Initial implementation (`fbdf41c`, 2021-03-12):
  `SaveAs(taskFileDir & "temp.cst", False)` followed by `Quit`.
- Updated implementation (`e37571e`, 2021-04-27):
  `Backup(taskFileDir & "temp.cst")` followed by `Quit`.
- Parameter-only preprocessing (`data/modelPreprocessT.vb`): bare `Quit`.
- Parameter reading (`data/readParamsT.vb`): `Save()` followed by `Quit`.

Therefore, the remembered behaviour was provided by ordinary `Quit` when the
project structure was not dirty, or by explicitly saving/backing up before
`Quit`; it was not a distinct discard-exit method in the checked source or Git
history.
