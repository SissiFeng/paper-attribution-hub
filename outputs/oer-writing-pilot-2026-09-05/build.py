"""Rebuild a curated writing pilot from persisted source excerpts. No model calls.
Run: python3 outputs/oer-writing-pilot-2026-09-05/build.py
Annotations are analyst proposals, not human-reviewed gold or general extraction rules.
"""
import hashlib, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
SOURCE = ROOT / 'outputs/domain-adapters/oer-electrocatalysis/0.3.3-pre-review/knowledge'
chunks = {r['scientific_chunk_id']: r for r in map(json.loads, (SOURCE/'scientific_chunks.jsonl').read_text().splitlines())}
papers = {r['paper_id']: r for r in map(json.loads, (SOURCE/'paper_records.jsonl').read_text().splitlines())}
A='scichk_117c432267e35874'
B='scichk_24abe194700e1bec'
C='scichk_4076e6f04ad62c74'
D='scichk_fe79dcc02f0633f1'
rows=[]
def add(id, chunk, start, stop, role, fact, template, condition, boundary, voice, rhythm, terms):
    c=chunks[chunk]; text=c['text']; lo=text.index(start)
    hi=text.index(stop,lo)+len(stop)
    quote=text[lo:hi]
    rows.append(dict(id=id,paper_id=c['paper_id'],doi=papers[c['paper_id']]['doi'],chunk_id=chunk,
        source_file=str((SOURCE/'scientific_chunks.jsonl').relative_to(ROOT)),
        char_start=lo,char_end=hi,offset_convention='zero-based Python Unicode, end exclusive, relative to chunk text',
        source_text_sha256=hashlib.sha256(text.encode()).hexdigest(),quote=quote,
        scientific_fact=fact,rhetorical_role=role,template=template,applicable_when=condition,
        must_not_infer=boundary,voice=voice,rhythm=rhythm,domain_terms=terms,
        annotation_status='analyst_proposal_not_human_gold',text_quality='selected_span_readable; surrounding_document_not_certified'))
add('A1',A,'Understanding the relationship','need to be identified.','问题分解','作者将结构—功能关系问题具体化为识别同一组成的可行多晶型。','To understand [relationship], we first need to identify [prerequisite objects].','研究目标确实依赖所列前置问题。','不能把某篇文章的前置条件写成所有材料研究的必要条件。','非人称陈述＋被动必要性','先提出关系，再限定任务',['structure–function relationship','polymorph'])
add('A2',A,'Herein, we report','IrO2 and IrO3.','贡献定位','作者报告用于识别电化学稳定铱氧化物多晶型的主动学习算法。','We develop [method] to identify [target] under [scope].','方法和目标在本研究中真实存在。','作者声称可推广不等于已经跨材料验证。','第一人称主动','单句集中交代方法、对象与范围',['active learning','electrochemical stability'])
add('A3',A,'To test the algorithms performance','rate of discovery.','对照验证','该文报告相对随机搜索至少两倍的发现速率。','Against [baseline], [method] achieved [measured change] in [defined metric].','指标、预算、搜索空间和比较对象可核查。','该数值属于原论文；不代表本项目结果，也不等于计算速度提升两倍。','目的短语＋第一人称主动','先说明检验目的，再给比较和量化结果',['random search','rate of discovery'])
add('A4',D,'The exact improvement','discussed recently. 62,63','结论限定','作者指出理论过电位改善幅度依赖DFT理论层级及自旋极化处理。','The magnitude of [predicted effect] depends on [modelling choices].','有敏感性分析或可引用依据支持该依赖。','不能把理论过电位写成实测性能；不能凭模板虚构敏感性结果。','非人称陈述','结尾补充条件，收窄数值结论',['theoretical overpotential','DFT','spin polarization'])
add('B1',B,'Moreover, experimental data','experimental methodologies.','数据缺口','作者指出实验数据稀缺，且报告标准不统一使汇总困难。','Available [data] are limited, while inconsistent [reporting practice] complicates [integration task].','本研究语料审计或文献能够支撑这个缺口。','这是作者对背景的概括，不能当作本项目已测得的数据质量结论。','非人称陈述','让步插入语后接两项关联困难',['experimental data','reporting standards'])
add('B2',B,'To tackle this challenge','perovskite oxide electrocatalysts.','缺口回应','作者提出以钙钛矿氧化物催化剂阳离子信息为中心的迁移学习方案。','To address [specific limitation], we use [approach] organized around [shared representation].','所选表征与前述缺口存在明确联系。','不能从转折连接词推断方案已经解决全部数据困难。','目的短语＋第一人称主动','紧接缺口，用一句话给核心方案',['transfer learning','cation information','perovskite oxide'])
add('B3',B,'This approach leverages','perovskite compositions.','方法机制','作者说明用预训练模型将OER数据与其他领域的数据结合。','The approach connects [target data] with [source data] through [transfer mechanism].','来源、目标和迁移过程可以明确描述。','跨领域数据结合本身不证明正迁移。','方法作主语的主动句','承接方案，展开知识来源和覆盖范围',['pre-trained models','OER data'])
add('B4',B,'Our approach demonstrates','OER catalysts.','研究收束','作者将迁移学习与主动学习的组合归结为应对数据限制、预测OER催化剂。','Within [evaluated scope], [combined approach] supports [evidence-backed outcome].','有本研究验证结果且明确限定测试范围。','原文的强结论不应原样套用；无验证时只能写研究目标。','方法作主语的主动句','将方法组合与目标重新汇合',['transfer learning','active learning','prediction'])
add('C1',C,'However, an important issue','industrial applications.','转化缺口','作者提出需要把高通量筛选的命中组成迁移到更接近工业应用的条件。','A remaining challenge is to transfer [screening findings] to [more relevant setting].','筛选环境与使用环境确实存在差异。','接近应用的测试不等于工业应用验证。','非人称问题陈述','转折后把关注点从筛选转向迁移',['hit compositions','high-throughput screening'])
add('C2',C,'The first step in this process','in this contribution.','桥接验证设计','作者将薄膜高通量表征到旋转圆盘电极测量作为迁移的第一步。','We test this transfer by moving from [screening setup] to [defined validation setup].','已经执行所述桥接测量。','一个桥接步骤不能代表完成整个应用转化链条。','条件式阶段描述＋被动完成说明','先限定为第一步，再具体列出测试方式',['thin films','rotating disk electrode'])
add('C3',C,'We demonstrate that thin-film','existing electrochemical techniques.','证据与意义连接','作者声称薄膜筛选结果可迁移至颗粒催化剂，并据此说明测试兼容性。','Agreement between [source setting] and [target setting] supports [bounded transfer claim].','存在可核查的跨设置比较；本例仅抽取作者陈述。','本次未重算其迁移可靠性，不能推广到其他组成体系。','第一人称主动＋结果解释','先给结果，再说明有限的方法学意义',['particulate catalysts','transferability'])
add('C4',C,'However, analysis of only one ML','targets are correlated.','限制与原因','单个材料库中的组成梯度相关，使元素作用和活性趋势难以独立判断。','A single [design] cannot resolve [effect] because [confounding structure].','设计结构或数据支持该混杂解释。','不能把共变关系直接写成元素的独立因果贡献。','非人称否定＋原因从句','先指出不可判定的目标，再解释结构性原因',['composition gradients','activity trends','confounding'])
relations=[('A1','A2','motivates'),('A2','A3','evaluated_by'),('A3','A4','complements_with_scope_caveat'),('B1','B2','motivates'),('B2','B3','elaborated_by'),('B3','B4','summarized_by'),('C1','C2','addressed_by'),('C2','C3','followed_by_author_claim'),('C3','C4','complements_with_design_caveat'),('A1','B1','analogous_problem_framing'),('B1','C1','analogous_gap_framing'),('A4','C4','analogous_scope_control')]
for r in rows:
    t=chunks[r['chunk_id']]['text']
    assert t[r['char_start']:r['char_end']]==r['quote']
    assert len(r['quote'])>30
    assert '|' not in r['quote']
    assert hashlib.sha256(t.encode()).hexdigest()==r['source_text_sha256']
assert len({r['id'] for r in rows})==12
assert len({r['paper_id'] for r in rows})==3
(OUT/'writing_units.jsonl').write_text('\n'.join(json.dumps(r,ensure_ascii=False) for r in rows)+'\n')
edges=[dict(source=a,target=b,relation=k,status='analyst_interpretation',basis='rhetorical interpretation; not learned cooccurrence or causal evidence') for a,b,k in relations]
(OUT/'relations.json').write_text(json.dumps(edges,ensure_ascii=False,indent=2)+'\n')
selected={r['chunk_id'] for r in rows}
(OUT/'source_excerpts.jsonl').write_text('\n'.join(json.dumps(chunks[k],ensure_ascii=False) for k in sorted(selected))+'\n')
manifest=dict(source_package='0.3.3-pre-review',papers=[papers[k] for k in sorted({r['paper_id'] for r in rows})],unit_count=len(rows),edge_count=len(edges),selection='purposive readable-span pilot; not full-paper close reading',excluded_paper='10.1021/acscentsci.3c01009: inspected chunks contain severe column/table interleaving',source_files_sha256={n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in ['scientific_chunks.jsonl','paper_records.jsonl']},human_reviewed=False,writing_improvement_evaluated=False)
(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
report=['# OER 论文：科学知识与写作知识双层试验','',
'基于本机 0.3.3-pre-review 包，完成 3 篇论文、12 个精选片段的人工式分析提案。不是全文精读，不是期刊偏好统计；未进行独立人工审核，也未证明写作质量提升。原文按本地提取版本保留，尚未对照出版社PDF逐字校订。','',
'## 选材与覆盖','',
'|论文|本次可用部分|未覆盖或限制|','|---|---|---|',
'|铱氧化物主动学习（A）|摘要、结果末尾的理论条件限定|结果图注有乱码，仅保留连续可读句子|',
'|钙钛矿迁移学习（B）|引言中的缺口—方案—机制—收束|分块开头不完整；不把引言收束冒充全文结论|',
'|高熵氧化物薄膜到颗粒（C）|转化动机、验证设计、设计限制|摘要串栏，未提取摘要模板|','',
'人机协作论文 10.1021/acscentsci.3c01009 的抽查片段串栏严重，本次排除。每篇仅选可读片段，因此不能据此估计全文风格、句长分布、作者习惯或期刊偏好。','',
'## 两层之间怎么关联','',
'同一个原文片段同时连接科学陈述和写作功能。模板是本次抽象生成的表达结构，不是原文引句；所有领域事实仍归属于原论文。语态与节奏标签只描述选中片段。','',
'## 12个可追溯零件','']
for r in rows:
    report += [f"### {r['id']} · {r['rhetorical_role']}",'',f"来源：[论文](https://doi.org/{r['doi']})；`{r['chunk_id']}`，字符 [{r['char_start']}, {r['char_end']})。",'',f"> {r['quote']}",'',f"**科学层：** {r['scientific_fact']}",'',f"**写作层：** {r['template']}",'',f"**语态与节奏：** {r['voice']}；{r['rhythm']}。",'',f"**适用条件：** {r['applicable_when']}",'',f"**不能推出：** {r['must_not_infer']}",'']
report += ['## 小型关系网络','', '以下12条边由本次分析提出，尚未经过共现统计或独立审核。跨论文边表达功能相似，不表示科学结论互相支持。','', '```mermaid','graph LR']
report += [f'  {e[0]} -->|{e[2]}| {e[1]}' for e in relations]
report += ['```','', '## 检索与组装示范','',
'检索意图：写一段关于数据驱动OER研究的文献综合，同时保留比较基线和适用边界。人工选取 B1、A3、C1、C2、C4。','',
'**英文示范（文献综合，不是你的新研究结果）：**','',
'Data-driven OER studies face challenges in both assembling evidence and transferring screening findings to new test settings. The perovskite transfer-learning study identifies scarce experimental data and inconsistent reporting as barriers to data integration [B1]. In the iridium-oxide study, the authors assess search efficiency against random selection and report at least a twofold increase in discovery rate [A3]. The high-entropy-oxide study addresses a different validation question: whether findings from thin-film screening carry over to particulate catalysts, using rotating-disk-electrode measurements as an initial bridge [C1–C2]. Its discussion of correlated composition gradients also illustrates why screening trends should not automatically be interpreted as independent elemental effects [C4].','',
'**中文说明：** 这段按“共同困难→具体比较→另一类验证→解释边界”组织。未把不同论文的数值相互比较，也未生成本项目的新结果。第一句为跨论文综合判断，其余句子可逐一回到上述零件核查。','',
'**留给本研究的结构模板：**','',
'Because [documented limitation], we developed [actual method] for [defined task]. We evaluated it against [baseline] under [matched conditions], obtaining [verified result]. We then examined transfer from [source setting] to [target setting] using [completed bridge experiment]. These results support [bounded claim]; [unresolved condition] remains to be tested.','',
'方括号必须由本研究证据填充；缺少对照、桥接实验或结果时，应删除相应句子或改为研究计划。','',
'## 这次能证明什么','',
'- 能证明已有分块可以承载“科学事实—写作功能—适用条件—出处”的双层记录，并支持小规模手工检索与组装。',
'- 12/12 引文的字符偏移和源文本哈希通过程序检查；这只证明对本地源文本的可追溯性。',
'- 不能证明抽取科学准确率、生成写作优越性、作者风格或期刊偏好；没有开展盲评或模型对照。',
'- 当前最大先决问题是原文提取质量。扩展前应修复串栏并回查公式，而不是直接增加维度。','',
'## 文件与复现','',
'运行 `python3 outputs/oer-writing-pilot-2026-09-05/build.py` 可从本地原包重建产物；这是固定样例的提取与校验器，不是通用自动精读模型。',
'`writing_units.jsonl` 保存结构化零件；`relations.json` 保存关系；`source_excerpts.jsonl` 保存使用的源分块；`manifest.json` 保存论文身份和输入哈希；`validation.json` 保存核验结果。']
(OUT/'试读报告.md').write_text('\n'.join(report)+'\n')
(OUT/'validation.json').write_text(json.dumps(dict(exact_span_checks_passed=12,unique_units=12,papers=3,edges=12,human_gold=False,scientific_accuracy_evaluated=False,writing_benefit_evaluated=False),indent=2)+'\n')
print(json.dumps(dict(output=str(OUT),units=len(rows),papers=3,span_checks='12/12 passed'),ensure_ascii=False))
if __name__=='__main__': pass
