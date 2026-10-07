export type NavigationItem = {
  to: string;
  label: string;
  description: string;
  keywords: string;
  group: string;
  access: 'public' | 'member' | 'admin';
  end?: boolean;
};

export const NAVIGATION: NavigationItem[] = [
  {to:'/papers',label:'Papers',description:'Browse publications, evidence and Wiki.',keywords:'论文 文献 阅读 wiki',group:'Research',access:'public'},
  {to:'/attribution',label:'Paper attribution',description:'Review classifications and attribution evidence.',keywords:'归属 分类 审核',group:'Research',access:'admin',end:true},
  {to:'/queue',label:'Review Queue',description:'Work through papers awaiting review.',keywords:'审核 队列 待处理',group:'Research',access:'admin'},
  {to:'/discovery',label:'Discovery',description:'Inspect publication discovery and candidates.',keywords:'发现 候选 新论文',group:'Research',access:'admin'},
  {to:'/retrieval',label:'Graph RAG',description:'Explore evidence retrieval and graph context.',keywords:'检索 问答 图谱 rag',group:'Research',access:'admin'},
  {to:'/research',label:'My research',description:'Private notes, comparisons, projects and method maps.',keywords:'我的科研 笔记 收藏 项目 比较 方法 地图 提醒 reading',group:'Research',access:'member'},
  {to:'/insights',label:'Insights',description:'Research patterns and data stories.',keywords:'洞察 分析 趋势',group:'Analytics',access:'admin'},
  {to:'/growth',label:'Net Growth',description:'Follow the growth of the research network.',keywords:'增长 网络',group:'Analytics',access:'admin'},
  {to:'/institution-comparison',label:'Institution Compare',description:'Compare institutional research contributions.',keywords:'机构 对比 大学',group:'Analytics',access:'admin'},
  {to:'/timeline',label:'Timeline',description:'Explore publication history over time.',keywords:'时间线 历史',group:'Analytics',access:'admin'},
  {to:'/sankey',label:'Sankey',description:'Trace flows across attribution categories.',keywords:'桑基 流向',group:'Analytics',access:'admin'},
  {to:'/impact',label:'Impact',description:'Inspect publication and citation impact.',keywords:'影响 引用',group:'Analytics',access:'admin'},
  {to:'/drift',label:'Drift',description:'Inspect changes in research themes.',keywords:'漂移 主题 变化',group:'Analytics',access:'admin'},
  {to:'/transfer',label:'Knowledge Transfer',description:'Explore connections across research areas.',keywords:'知识 迁移',group:'Analytics',access:'admin'},
  {to:'/transfer-studio',label:'Transfer Studio',description:'Investigate possible research transfers.',keywords:'迁移 工作室',group:'Analytics',access:'admin'},
  {to:'/kb',label:'Knowledge Base',description:'Browse structured research knowledge.',keywords:'知识库',group:'Analytics',access:'admin'},
  {to:'/multi-graph',label:'Multi-Graph',description:'Explore connected research entities.',keywords:'多图 图谱',group:'Network',access:'admin'},
  {to:'/network',label:'Co-Author',description:'Explore co-authorship and collaboration.',keywords:'合作 作者 网络',group:'Network',access:'admin'},
  {to:'/geographic',label:'Geographic',description:'View the geographic research network.',keywords:'地理 国家 地图',group:'Network',access:'admin'},
  {to:'/people',label:'People Grid',description:'Browse researchers and their work.',keywords:'人员 研究者 成员',group:'Team',access:'admin'},
  {to:'/lint',label:'Lint Report',description:'Inspect metadata quality checks.',keywords:'质量 校验',group:'Operations',access:'admin'},
  {to:'/duplicates',label:'Duplicates',description:'Review potentially duplicate papers.',keywords:'重复 去重',group:'Operations',access:'admin'},
  {to:'/evidence-gaps',label:'Evidence Gaps',description:'Find missing evidence and source gaps.',keywords:'证据 缺失',group:'Operations',access:'admin'},
  {to:'/pipeline',label:'Pipeline',description:'Inspect ingestion and processing status.',keywords:'入库 处理 运行 状态',group:'Operations',access:'admin'},
  {to:'/report',label:'Report',description:'Open research reporting tools.',keywords:'报告 汇总',group:'Operations',access:'admin'},
  {to:'/eval',label:'Eval',description:'Inspect classification evaluation results.',keywords:'评估 测试',group:'Operations',access:'admin'},
];

export function navigationItems(admin: boolean): NavigationItem[] {
  return admin ? [...NAVIGATION,{to:'/research?manage=members',label:'Manage access',description:'Manage PAS members and administrator roles.',keywords:'权限 管理 成员',group:'Operations',access:'admin'}] : NAVIGATION;
}

export function navigationActive(item: NavigationItem, pathname: string, search: string, admin: boolean) {
  if (pathname==='/') return item.to===(admin?'/attribution':'/papers');
  const managing=admin && pathname==='/research' && new URLSearchParams(search).get('manage')==='members';
  if (item.to.includes('?')) return managing;
  if (managing && item.to==='/research') return false;
  return pathname===item.to || (!item.end && pathname.startsWith(item.to+'/'));
}

export function findNavigation(items: NavigationItem[], query: string) {
  const words=query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  return items.filter(item=>words.every(word=>`${item.label} ${item.description} ${item.group} ${item.keywords}`.toLocaleLowerCase().includes(word)));
}

export function navigationShortcut(event: {key:string;metaKey:boolean;ctrlKey:boolean;altKey:boolean;shiftKey:boolean;isComposing:boolean;repeat:boolean}) {
  return !event.isComposing && !event.repeat && !event.altKey && !event.shiftKey && (event.metaKey||event.ctrlKey) && event.key.toLowerCase()==='k';
}
