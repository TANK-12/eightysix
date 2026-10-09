# Claude app: look and feel critic report
date: 2026-10-07 · for: both · reviewer: critic subagent of helper-2; 51 screenshots in /tmp/critic-look/shots/ (classic and Enjoy at 1500/1100/760 wide, empty app); scripts /tmp/critic-look/{look,probe,timeapi}.py

Real defects, ranked:
1. Enjoy below 900px has no navigation: enjoy.css:259-261 hides #e-rail with no replacement. Fix: rail becomes a top strip: #e-rail{flex-direction:row;align-items:center;overflow-x:auto;padding:10px 14px;border-right:0;border-bottom:1px solid var(--border)} #e-rail .e-rail-head,#e-rail-projects{display:none} .e-rail-foot{flex-direction:row;border-top:0;padding:0}
2. Whole classic page waits on /api/options (app.js:985), which runs `claude --version` (10 s timeout) + a Browser probe (2 s) at web_app.py:118-131: list appeared after 10.2 s with the fake CLI; ~1-3 s blank sidebar with the real one. Enjoy same (enjoy.js:880). Fix: version worked out once at server start in a thread; loadChats() in parallel with /api/options.
3. Unstyled scrollbars everywhere (biggest "cheap" look). Add to app.css and enjoy.css: *{scrollbar-width:thin;scrollbar-color:#3a3f4b transparent} ::-webkit-scrollbar{width:8px;height:8px} ::-webkit-scrollbar-button{display:none} ::-webkit-scrollbar-track,::-webkit-scrollbar-corner{background:transparent} ::-webkit-scrollbar-thumb{background:#3a3f4b;border-radius:8px;border:2px solid transparent;background-clip:padding-box}. Check in the real WebKitGTK window.
4. Tab bar has a vertical scrollbar (#tabs scrollHeight 45 vs 44; app.css:200-201). Fix: .tabs{overflow-y:hidden;scrollbar-width:none}; at 760 the + button wraps to a second row: keep it in the row.
5. Markdown tables not drawn (claude_common.js has no table rule). Add one, styled: .bubble table{border-collapse:collapse} .bubble td,.bubble th{border:1px solid var(--border);padding:4px 8px}
6. setInterval(refreshTabs, 4000) at app.js:1036 polls while hidden (others at 1023, 1189, enjoy.js:872 are gated). Gate it.
7. Classic header eats the chat on smaller windows: 2 rows at 1500, 4 (~180px) at 1100, 5 (~215px) at 760, ~310px log left. Fix: header flex-wrap:nowrap, cwd input flex:1 1 120px;min-width:0; Full screen and Close app become small icon pills in the tab-bar row.
8. Enjoy's fixed Close app / Full screen pills (shared/forge_chrome.js) cover content (loose-task open links, roadmap timestamps). Fix in enjoy.css: #e-main{padding-bottom:64px}.
9. Enjoy's Limits panel stays open when switching task (hash-only route). Close E.run's details in route().
10. Classic sidebar at 950px tall gives the chat list ~260px (five open Web logins rows ~280px). Fix: #fold-web starts collapsed; #chats min-height:40%; account sections flex:none;max-height:35%.
11. Avatar pane wastes 340px when the avatar is off (now the default). Fix: with .stage-off, shrink #stage-pane to ~220px or start collapsed.
12. A crashed turn is plain red centred text with no card, and not in Enjoy's needs-you list. Fix: .toolcard.error look; failed turns listed under needs you.
Taste:
13. Project name ending in punctuation gets a second one ("40 chars!."); long names wrap to 3 lines at 32px: -webkit-line-clamp:2.
14. At 760 Enjoy knobs are 96-106px wide: .e-knob min-width:150px (blank values mostly item 2).
15. Limits sliders sit at 20 / 1 while the box says "auto": hide the thumb until a value is set.
Not checked: avatar with animation on (WebGL); hidden-window behaviour inside real WebKitGTK. Confirmed by DOM probe: 1, 2 (10.2 s is with the fake CLI), 4, 5, 9; rest from screenshots or code.
