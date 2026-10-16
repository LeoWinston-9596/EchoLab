/* Shared UI translations; learning content is intentionally left unchanged. */
(() => {
  "use strict";
  const EN = {
  "素材库": "Library",
  "看视频学英语": "Learn with video",
  "点任意一期开始学。进度会自动记住。刷视频时点书签即可入队,会自动解析。": "Choose an episode to start. Progress is saved automatically. Use the bookmark to queue videos.",
  "搜标题、主题…": "Search titles and topics…",
  "全部": "All",
  "未学完": "In progress",
  "★1-2 简单": "★1–2 Easy",
  "★4-5 有挑战": "★4–5 Challenging",
  "最新加入": "Newest first",
  "最早加入": "Oldest first",
  "时长 短→长": "Shortest first",
  "时长 长→短": "Longest first",
  "按作者": "By author",
  "回到素材库": "Back to library",
  "上一个素材": "Previous episode",
  "下一个素材": "Next episode",
  "↑ 上一句": "↑ Previous",
  "▶ 播放": "▶ Play",
  "下一句 ↓": "Next ↓",
  "更多设置": "More settings",
  "播放与显示设置": "Playback and display",
  "完成": "Done",
  "↺ 重听本句": "↺ Replay sentence",
  "🔁 单句循环": "🔁 Loop sentence",
  "⏸ 单句暂停": "⏸ Pause after sentence",
  "双语": "Bilingual",
  "英": "EN",
  "中": "中文",
  "🎨 标注": "🎨 Highlight",
  "🎯 跟随": "🎯 Follow",
  "空格": "Space",
  "字幕": "Subtitles",
  "单词": "Words",
  "语块": "Chunks",
  "收藏": "Favourites",
  "单个的词,一个个记": "Individual vocabulary words",
  "lexical chunks:短语、短语动词、搭配、口语句式、话语标记——整块记住,不要拆开背": "Learn phrases, phrasal verbs, collocations, patterns and discourse markers as whole expressions",
  "音频": "Audio",
  "词卡": "cards",
  "已学完": "Completed",
  "全部作者": "All authors",
  "期": "episodes",
  "没有匹配的内容。": "No matching episodes.",
  "正在解析": "Processing",
  "排队中": "Queued",
  "已完成": "Completed",
  "失败": "Failed",
  "已跳过": "Skipped",
  "队列会自动解析": "Queue processing automatically",
  "队列(解析未启动,请用启动脚本或 python serve.py)": "Queue paused — start with python serve.py",
  "重试": "Retry",
  "去掉": "Dismiss",
  "素材库还是空的。用书签存一条视频,解析完会出现在这里。": "Your library is empty. Queue a video with the bookmark; it will appear here after processing.",
  "读不到素材库。请用 ": "Cannot load the library. Start it with ",
  " 启动,不要直接双击打开本文件。": " rather than opening this file directly.",
  "素材库还是空的。": "Your library is empty.",
  "先跑 ": "Run ",
  " 看演示。": " to try the demo.",
  "这一期读取失败:": "Could not load this episode:",
  "文件应在 ": "Expected file: ",
  "这一期是纯音频素材": "Audio-only episode",
  "右侧字幕、单词、语块功能完全一样": "Subtitles, words and chunks work the same way.",
  "语速 ": "Speed ",
  " 词/分": " wpm",
  "建议 ": "Suggested ",
  " 分钟": " minutes",
  "YouTube 嵌入 · 未下载": "YouTube embed · no download",
  "收藏的句子已按新的划分自动对上,不用重新收藏": "Saved sentences have been matched to the new segmentation.",
  "上次听到第 ": "Last listened: sentence ",
  " 句": "",
  "继续": "Resume",
  "从头": "Start over",
  "▶ 播这句": "▶ Play sentence",
  "🔁 循环": "🔁 Loop",
  "★ 已收藏": "★ Saved",
  "☆ 收藏": "☆ Save",
  "复制": "Copy",
  "已复制": "Copied",
  "⏸ 暂停": "⏸ Pause",
  "短语": "Phrases",
  "短语动词": "Phrasal verbs",
  "搭配": "Collocations",
  "口语句式": "Patterns",
  "话语标记": "Discourse markers",
  "🔊 美": "🔊 US",
  "🔊 英": "🔊 UK",
  "美 /": "US /",
  "英 /": "UK /",
  "▶ 原句:": "▶ Source: ",
  "这一期没有单词卡片。": "No word cards in this episode.",
  "去「语块」看看,": "Try the Chunks tab.",
  "口语素材的价值多半在那边。": "Spoken expressions are often best learned in groups.",
  "这一期没有语块卡片。": "No chunk cards in this episode.",
  "收藏的句子 ": "Saved sentences ",
  "收藏的词条 ": "Saved expressions ",
  "还没有收藏。": "No favourites yet.",
  "点字幕里的「☆ 收藏」,或单词/语块卡片上的 ☆。": "Select ☆ Save on a subtitle or ☆ on a vocabulary card.",
  " 播放 · ": " Play · ",
  " 上下句 · ": " Previous/next · ",
  " 重听 ·": " Replay ·",
  " 循环 · ": " Loop · ",
  " 单句暂停 · ": " Pause after sentence · ",
  " 上/下一个素材": " Previous/next episode",
  "安装书签": "Bookmark setup",
  "把这个拖到书签栏": "Drag this to your bookmarks bar",
  "📥 存进 EchoLab": "📥 Save to EchoLab",
  "拖一次就好。以后在 YouTube / TikTok / 抖音的视频页面点它一下,链接就进了本地队列。": "Install once, then click the bookmark on a video page to add its URL to the local queue.",
  "拖不动的话:右键书签栏 → 添加网页 → 名称随便填,网址粘贴下面这段。": "Alternatively, add a bookmark manually and paste the following code as its URL.",
  "然后怎么处理": "Processing",
  "什么都不用再开。这个窗口已经在守着队列,书签点进去的视频会自动解析,\n解析完刷新素材库就能看到。": "The running server watches the queue automatically. Refresh the library once processing finishes.",
  "只想提供网页、暂时不解析时,用 ": "To serve pages without processing, use ",
  "。": ".",
  "几个前提": "Requirements",
  "这个服务(": "Keep the server (",
  ")得开着,书签才有地方送。": ") running so the bookmark can reach it.",
  "浏览器建议用 Chrome 或 Edge。它们把 ": "Chrome or Edge are recommended. They treat ",
  " 当作可信来源,\nHTTPS 页面也能访问本地服务;Safari 会拦,拦了会自动改为新开标签页兜底。": " as a trusted origin. If a browser blocks the request, the bookmark opens a new tab as a fallback.",
  "YouTube 走取字幕 + 嵌入播放,不下载;TikTok / 抖音需要你自行安装\n": "YouTube prefers captions and embedded playback; other supported platforms require ",
  ",并自行判断是否符合对应平台的条款。": " installed separately. Follow the source platform’s terms.",
  "手机 / 平板怎么打开": "Phones and tablets",
  "不能用 localhost": "Use the computer’s LAN address",
  " —— 在手机上 localhost 指的是手机自己。要用这台电脑的\n局域网地址:": " — localhost on a phone refers to the phone itself:",
  "连不上的话多半是 Windows 防火墙拦了入站。用管理员身份打开 PowerShell 执行一次:": "If Windows Firewall blocks access, a maintainer can allow this port in an administrator PowerShell:",
  "另外确认手机和电脑连的是同一个 Wi-Fi,且路由器没有开「AP 隔离 / 访客网络」——\n那个功能会禁止同网设备互访。": "Connect both devices to the same Wi-Fi and disable client isolation for trusted devices.",
  "令牌只在你本机,换了机器要重新拖一次书签。": "The bookmark token belongs to this computer. Reinstall the bookmark on a new computer."
};
  const NORMAL = Object.fromEntries(Object.entries(EN).map(([k,v])=>[k.replace(/\s+/g," "),v]));
  const KEY = "echolab.language";
  let lang;
  try { lang = localStorage.getItem(KEY); } catch (_) {}
  if (!['en','zh-CN'].includes(lang)) lang = navigator.language?.startsWith('zh') ? 'zh-CN' : 'en';
  const t = text => lang === 'en' ? (EN[text] ?? NORMAL[text.replace(/\s+/g," ")] ?? text) : text;
  function apply(root = document) {
    document.documentElement.lang = lang;
    root.querySelectorAll('[data-i18n]').forEach(el => { el.textContent = t(el.dataset.i18n); });
    root.querySelectorAll('[data-i18n-title]').forEach(el => { el.title = t(el.dataset.i18nTitle); });
    root.querySelectorAll('[data-i18n-placeholder]').forEach(el => { el.placeholder = t(el.dataset.i18nPlaceholder); });
    document.querySelectorAll('[data-language]').forEach(el => { el.value = lang; });
  }
  function setLanguage(value) {
    if (!['en','zh-CN'].includes(value)) return;
    lang = value;
    try { localStorage.setItem(KEY, lang); } catch (_) {}
    apply();
    window.dispatchEvent(new CustomEvent('echolab:language'));
  }
  window.EchoI18n = {t, apply, setLanguage, get language() { return lang; }};
  document.addEventListener('DOMContentLoaded', () => {
    apply();
    document.querySelectorAll('[data-language]').forEach(el => el.addEventListener('change', () => setLanguage(el.value)));
  });
  window.addEventListener('storage', e => { if (e.key === KEY && ['en','zh-CN'].includes(e.newValue)) setLanguage(e.newValue); });
})();
