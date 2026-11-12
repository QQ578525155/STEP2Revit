# STEP2Revit

STEP2Revit converts STEP and SolidWorks hardware parts — bolts, brackets, and fittings — into parametric Revit families (`.rfa`). It is free and open source, built for the Devpost Kiroween 2026 hackathon (Frankenstein category).

The pipeline is STEP in, a neutral JSON description (solids, bounding dimensions, key features and parameters), then a parametric `.rfa`. This package implements the STEP parser and the family builder. The builder reads only the JSON document and has to run inside Revit on Windows. GitHub Actions does not run Revit. The cloud environment used to prepare the demo does not have Revit either. No `.rfa` was generated in CI or in the cloud, and this repository does not contain one.

Libraries and automation stay free and open source. The STEP kernel is `cadquery-ocp` (Apache-2.0). The Revit host is [pyRevit](https://github.com/pyrevitlabs/pyRevit). CI is GitHub Actions. The project does not call a paid API or a proprietary geometry kernel. `.kiro/` stays committed. The license is MIT.

The contract is [`.kiro/specs/step-to-rfa-pipeline/requirements.md`](.kiro/specs/step-to-rfa-pipeline/requirements.md). How the parser recognizes a cylinder, a hole, and an extrusion is [`.kiro/specs/step-to-rfa-pipeline/design.md`](.kiro/specs/step-to-rfa-pipeline/design.md). How the builder turns that JSON into a family is [`.kiro/specs/step-to-rfa-pipeline/builder.md`](.kiro/specs/step-to-rfa-pipeline/builder.md). The three-minute demo script is [`docs/demo-script.md`](docs/demo-script.md). There is no video file in this repository. The Revit half of that script is narration of the click path below.

## Walkthrough

A reviewer can follow the install and the parse on Linux, macOS, or Windows. The family step needs Revit on Windows. The steps below do not produce a `.rfa` unless you run them inside Revit.

### 1. Editable install

Python 3.11 or newer. From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
```

The package depends on `cadquery-ocp` (Open CASCADE bindings, Apache-2.0). The `[dev]` extra installs pytest and ruff.

### 2. Parse a STEP file to schema-1 JSON

The command-line entry is `python -m step2revit`. It reads one STEP part and writes the schema-1 document. It does not build a family.

```bash
python -m step2revit part.step part.json
```

```python
from step2revit import parse_step

document = parse_step("part.step", "part.json")
```

`part.step` must be STEP AP203, AP214, or AP242 (`.step` or `.stp`). `part.json` is schema 1. Lengths are millimetres. `source.length_unit` is the unit name from the STEP file before that conversion.

The repository does not commit STEP files. Tests generate them in `tests/step_samples.py` (see [tests/NOTICE](tests/NOTICE)). From the repository root, the cylinder those tests call `write_cylinder` is a shank of radius 5 mm and length 40 mm:

```python
from pathlib import Path
from tests.step_samples import write_cylinder

write_cylinder(Path("shank.step"))
```

```bash
python -m step2revit shank.step shank.json
```

`shank.json` has `schema_version` `"1"`, `units.length` `"mm"`, one `cylinder` feature (`cylinder_1`, axis along Z), and parameters `Cylinder1Diameter` (10) and `Cylinder1Length` (40). `shank.step` and `shank.json` are local output. `write_plate_with_hole` in the same module is the 40 mm by 30 mm by 5 mm plate with an 8 mm through hole. That document has `extrusion_1` and `hole_1`, with `Extrusion1Length` (5), `Hole1Diameter` (8), and `Hole1Depth` (5).

### 3. Build a Revit family

This step runs inside Revit on Windows. Revit is not installed in GitHub Actions or in this project's cloud environment. No `.rfa` was generated in CI or in the cloud.

1. Install [pyRevit](https://github.com/pyrevitlabs/pyRevit) (free and open source) and use its CPython engine on Python 3.11 or newer. Revit's own Python shell on Revit 2025 or newer also works.
2. Install this package into that Python with `python -m pip install -e .`, or run the script from this clone. The script adds `src` to `sys.path`. The builder does not import the STEP kernel, so Revit's Python does not need `cadquery-ocp`.
3. In pyRevit, add the folder `revit/STEP2Revit.extension` as a custom extension and reload. The button is STEP2Revit, then Build, then Build Family.
4. The button asks for the schema-1 JSON file and the output `.rfa` path. It loads `Metric Generic Model.rft` from `%ProgramData%\Autodesk\RVT <year>\Family Templates\English\`. Set `STEP2REVIT_TEMPLATE` when that file lives somewhere else. `STEP2REVIT_JSON` and `STEP2REVIT_RFA` skip the file prompts.

The script creates one loadable Generic Model family, extrudes each cylinder, prism, and hole, and binds every JSON length to a type parameter. It does not read STEP and does not use the network. The comment at the top of `revit/STEP2Revit.extension/STEP2Revit.tab/Build.panel/BuildFamily.pushbutton/script.py` states the same limit.

## Tests

```bash
pytest
```

`ruff check src tests revit` runs the same lint check as CI. The geometry tests generate small solids in-process (box, cylinder, plate with a hole) and do not download STEP files. See [tests/NOTICE](tests/NOTICE).

## License

MIT. See [LICENSE](LICENSE).

## 中文

STEP2Revit 把 STEP 零件，以及 SolidWorks 导出的五金件（螺栓、支架、配件），转成参数化的 Revit 族（`.rfa`）。项目自由、开源，参加 Devpost Kiroween 2026 黑客松的 Frankenstein 类别。

流水线是：STEP 进入，写出一份中立 JSON（实体、包围尺寸、关键特征和参数），再得到参数化的 `.rfa`。解析器是跨平台 Python，不需要安装 Revit。族构建器只读这份 JSON，并且必须在 Windows 上的 Revit 里运行。

自由与开源是约束。STEP 内核是 `cadquery-ocp`（Apache-2.0）。Revit 宿主是免费开源的 pyRevit。持续集成是 GitHub Actions。不调用付费 API，也不使用专有几何内核。许可证是 MIT。`.kiro/` 全部提交，不会被 gitignore。

GitHub Actions 和准备本演示的云环境都没有安装 Revit。CI 和云端都没有生成 `.rfa`，仓库里也没有生成的 `.rfa`。下面的 Revit 步骤只有在 Revit 里执行才会写出族文件。

审阅步骤与上面的英文 Walkthrough 相同。

1. 可编辑安装。Python 3.11 或更新版本，在仓库根目录执行：

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
```

2. 把 STEP 解析成 schema 1 的 JSON。命令行入口是 `python -m step2revit`。Python 入口是 `parse_step`。这一步不建族。

```bash
python -m step2revit part.step part.json
```

输入须为 STEP AP203、AP214 或 AP242（`.step` 或 `.stp`）。JSON 里的长度是毫米。`source.length_unit` 是换算前 STEP 文件里的单位名。仓库不提交 STEP 文件。测试在 `tests/step_samples.py` 里现场生成。在仓库根目录，`write_cylinder` 写出半径 5 mm、长度 40 mm 的圆柱，再交给上面的命令：

```python
from pathlib import Path
from tests.step_samples import write_cylinder

write_cylinder(Path("shank.step"))
```

```bash
python -m step2revit shank.step shank.json
```

`shank.json` 的 `schema_version` 为 `"1"`，参数是 `Cylinder1Diameter`（10）和 `Cylinder1Length`（40）。`shank.step` 和 `shank.json` 是本地输出。

3. 在 Windows 的 Revit 里建族。安装 pyRevit，使用它的 CPython（Python 3.11 或更新版本）。Revit 2025 及更新版本自带的 Python 也可以。把本包装进那个 Python：`python -m pip install -e .`，或者从本仓库运行脚本。脚本会把 `src` 加进 `sys.path`。构建器不导入 STEP 内核，Revit 的 Python 不需要 `cadquery-ocp`。在 pyRevit 里把 `revit/STEP2Revit.extension` 加为自定义扩展并重新加载。按钮是 STEP2Revit → Build → Build Family。模板是 `Metric Generic Model.rft`，默认在 `%ProgramData%\Autodesk\RVT <year>\Family Templates\English\`。`STEP2REVIT_TEMPLATE` 指向别处的模板。`STEP2REVIT_JSON` 和 `STEP2REVIT_RFA` 跳过文件对话框。脚本把每个圆柱、棱柱和孔挤出，并把每条 JSON 长度绑到族的类型参数。它不读 STEP，也不访问网络。

三分钟演示脚本在 [`docs/demo-script.md`](docs/demo-script.md)。仓库里没有视频文件。脚本里的 Revit 一段是口述点击路径，不是 Revit 录像。
