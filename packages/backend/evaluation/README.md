# 合成资料质量评测基础包

本包已经提供数据与资产校验、已有结果汇总和环境预检。**尚未接入真实生产检索/模型运行器，也没有真实质量基线。** `validate` 成功只证明评测资料合同成立；`summarize` 只统计提供的观测，不证明结果来自真实模型，不自动签署质量验收。

## 固定数据集

- 共60例：文档、代码、图片文字、多来源混合各15例。每类10例dev、5例holdout，60个独立资料组。
- 每类覆盖正向、无证据、资料冲突、版本更新和提示注入各3例，其中2例dev、1例holdout。按资料组隔离，重复资产指纹也不得跨split。
- 全部资料为本仓库合成样例，不含个人资料或第三方仓库。合成代码用 `sha256:<资产哈希>` 标识版本，**没有伪造Git commit**。更新样例显式区分当前与先前版本。
- `assets/` 保存 Markdown、Python、PNG及对应人工核对文字稿。图片文字稿用于OCR参考答案，不是机器OCR结果；图片由固定文字渲染，未调用图像模型。人工描述和OCR不混写。
- `cases.jsonl` 固定问题、预期事实、逐字引用、是否应拒答、来源版本及资产SHA256。合法引用只能证明文字存在，不能证明结论受支持。
- 合成集适合检查评测编排和边界，其同一主题的简单问题不代表真实业务分布。真实基线仍需更丰富资料、真实检索/模型观测和逐例人工核查。

## 离线使用

在 `packages/backend` 执行。可以使用已有且匹配锁的Python3.12环境，无需启动PostgreSQL、Redis、API或Worker。

```powershell
$py = '.venv\Scripts\python.exe' # 按主README建立Python3.12与锁文件一致的环境
& $py tools/evaluate_quality.py validate
& $py tools/evaluate_quality.py validate --split all
& $py tools/evaluate_quality.py preflight
```

默认返回40例开发集；`--split holdout` 或 `--split all` 必须显式指定。校验会核验完整60例资产和组隔离，但默认不把封存例纳入指标统计。开发过程中不要用封存答案调参。

路径必须相对数据集目录，拒绝绝对路径、`..`、Windows驱动器/反斜线、越界符号链接。缺失资产、SHA256漂移、重复ID、跨split资料、引用不存在、未知字段和非严格类型会失败。错误消息不回显JSON输入值。不要通过修改hash掩盖漂移；应审查数据更改及版本影响。

`preflight` 只检查Python版本、已安装包、PATH中的Tesseract及中英文语言包、进程环境中是否存在LLM凭据。它不读取 `.env`，不输出凭据，不探测业务数据库，不下载或加载模型，不发送网络请求。实际embedding维度和LLM连通性标为 `not_probed`，整体始终 `not_run`，原因包含 `production_adapter_not_implemented`。已有业务配置不因这个结果而失效。

## 汇总已有观测

已有结果采用JSONL，每行一个case，字段合同由 `EvaluationResult` 定义。要求 `dataset_hash`、`case_id`、`status`、`execution_mode`；`dataset_hash`必须记录观测生成时的固定数据集指纹，汇总前逐行核对，不能把旧结果改挂新资料。完成记录另有 `answer` 和布尔型 `refused`。`retrieved`/`citations` 的每项为来源ID、精确版本、逐字原文；`ocr_text` 按图片来源ID记录实际文字；`manual_support` 为人工检查的 `supported` 和 `total`。

下面生成**单条确定性示例观测**，用于检查汇总命令，不运行模型，不代表真实质量。结果目录被忽略，不能提交。

```powershell
New-Item -ItemType Directory -Force evaluation/reports | Out-Null
@'
import json
from pathlib import Path
from app.services.quality_evaluation import load_dataset
dataset = load_dataset('evaluation/cases.jsonl')
case = dataset.cases[0]
gold = case.expected_evidence[0]
source = next(item for item in case.sources if item.id == gold.source_id)
citation = {'source_id': source.id, 'version': source.version, 'quote': gold.quote}
row = {'dataset_hash': dataset.dataset_hash, 'case_id': case.id, 'status': 'completed', 'execution_mode': 'fixture',
       'answer': 'Synthetic fixture observation only', 'refused': False,
       'retrieved': [citation], 'citations': [citation]}
Path('evaluation/reports/example.results.jsonl').write_text(json.dumps(row) + '\n', encoding='utf-8')
'@ | & $py -
& $py tools/evaluate_quality.py summarize --results evaluation/reports/example.results.jsonl --mode fixture
```

省略 `--mode` 时只统计 `production` 标签，fixture/manual不混入同一分母；标签是输入者声明，不是对真实调用的鉴定。结果ID重复、未知/未选中的case、人工标注分子大于分母或未完成记录携带观测都会失败。封存观测不得混入默认开发报告。

每个指标都有value、numerator、denominator；没有观测时value为null。报告另列选中/完成/失败/未运行/缺失/其他mode数量，不能用缺失例填零或当通过。

- Recall@5：有检索观测的可回答例中，前5个候选包含的gold逐字证据比例，再按case取宏平均；相同证据重复命中只计一次。
- MRR：有检索观测的可回答例中，输入排名里第一个有效gold证据的倒数排名；没有命中为0。只有 `retrieved` 被省略时才不计分母。
- 正确拒答：应拒答且确实拒答 / 有完整观测的应拒答例；错误拒答：可回答却拒答 / 有完整观测的可回答例。
- OCR CER：Unicode字符编辑距离之和 / 人工文字稿字符数；保留换行与空格，不静默归一化。没有OCR观测时为null。
- 无效引用：错误来源、版本或不存在的逐字引用 / 提供的引用数，附原因诊断；无引用回答另列missing_citations，不自动视为事实错误。
- 陈述支撑率：人工确认支持的关键陈述 / 人工实际检查的关键陈述。缺少人工标注时为null；**不从引用合法性或模型自评推导**。

报告包含run_id、数据集hash、代码commit、code_dirty、models、参数、状态和未运行原因。当前没有真实执行记录，CLI的模型名称为null；`summarize` Python入口允许调用方提供已核实的模型名称。报告不复制原始答案、输入文本或供应商错误。若code_dirty为true，commit只标识基础版本，交付前仍需审查diff。

## 修改数据与验证

资产已作为固定样例保存。只有明确修改合成集时运行 `python evaluation/build_synthetic_dataset.py --write`，随后审查全部资产和hash差异；验证命令绝不自动重建样例。PNG重建使用Pillow及内置字体，不同版本可能改变字节，必须核对差异。

`.gitattributes` 禁止Git自动转换固定资产和cases.jsonl的换行字节，使Windows/Linux检出得到相同指纹；不要对这些资产执行批量格式化。

```powershell
& $py -m pytest tests/test_quality_evaluation.py -q -p no:cacheprovider
& $py -m ruff check app/services/quality_evaluation.py tests/test_quality_evaluation.py tools/evaluate_quality.py evaluation/build_synthetic_dataset.py
& $py -m mypy app/services/quality_evaluation.py
```

符号链接创建无权限时单独跳过并披露；其他路径与hash测试照常运行。测试临时目录跟随pytest环境设置，不修改测试fixture来绕过执行环境权限。

后续接入真实adapter时，应复用现有连接器/检索/限定来源问答，先确认隔离数据库与公开/合成资料范围；记录真实模型、关键参数、费用和超时，输出对应execution_mode观测。先跑开发基线、人工核查，再按失败最小优化，最后显式运行封存集。当前包没有自动候选采纳、生产迁移或部署逻辑。
