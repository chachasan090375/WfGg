from pathlib import Path
import re

path = Path('frontend/_worker.js')
src = path.read_text(encoding='utf-8')

new_css = r'''      style.textContent='@keyframes wfggTrainRide{0%{transform:translateX(-235px)}100%{transform:translateX(390px)}}@keyframes wfggWheelSpin{to{transform:rotate(360deg)}}@keyframes wfggBodyFloat{0%,100%{transform:translateY(0)}50%{transform:translateY(-1px)}}#wfggTrainPortalGate .wfgg-train-stage{position:relative;width:min(360px,86vw);height:104px;overflow:hidden}#wfggTrainPortalGate .wfgg-train-track{position:absolute;left:0;right:0;bottom:15px;height:3px;background:linear-gradient(90deg,transparent,rgba(235,235,235,.75) 8%,rgba(235,235,235,.75) 92%,transparent)}#wfggTrainPortalGate .wfgg-train-track:after{content:"";position:absolute;left:7%;right:7%;top:8px;height:3px;background:repeating-linear-gradient(90deg,rgba(190,190,190,.36) 0 12px,transparent 12px 25px)}#wfggTrainPortalGate .wfgg-train-sprite{position:absolute;left:0;bottom:25px;width:205px;height:68px;filter:drop-shadow(0 7px 12px rgba(0,0,0,.5));animation:wfggTrainRide 2.55s linear infinite}#wfggTrainPortalGate .wfgg-micheline{position:absolute;inset:0;animation:wfggBodyFloat .75s ease-in-out infinite}#wfggTrainPortalGate .wfgg-micheline svg{display:block;width:205px;height:68px;overflow:visible}#wfggTrainPortalGate .wfgg-micheline-wheel{transform-box:fill-box;transform-origin:center;animation:wfggWheelSpin .58s linear infinite}@media (prefers-reduced-motion:reduce){#wfggTrainPortalGate .wfgg-train-sprite{animation-duration:5.5s}#wfggTrainPortalGate .wfgg-micheline,#wfggTrainPortalGate .wfgg-micheline-wheel{animation:none}}';
'''

new_html = r'''      el.innerHTML='<div class="wfgg-train-stage" aria-hidden="true"><div class="wfgg-train-track"></div><div class="wfgg-train-sprite"><div class="wfgg-micheline"><svg viewBox="0 0 205 68" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Micheline ancienne"><defs><linearGradient id="wfggMichCream" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#f3e7c8"/><stop offset="1" stop-color="#cbbd9e"/></linearGradient><linearGradient id="wfggMichRed" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#a83d37"/><stop offset="1" stop-color="#642421"/></linearGradient><linearGradient id="wfggMichMetal" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ddd8cc"/><stop offset=".5" stop-color="#827f78"/><stop offset="1" stop-color="#4a4947"/></linearGradient></defs><path d="M18 17 Q28 7 49 6 H156 Q179 7 192 20 Q198 26 199 39 L196 49 H10 L8 35 Q8 24 18 17Z" fill="url(#wfggMichCream)" stroke="#e8dec7" stroke-width="1.3"/><path d="M9 35 H199 L196 50 H10Z" fill="url(#wfggMichRed)"/><path d="M24 14 Q31 9 49 8 H158 Q174 9 185 17" fill="none" stroke="rgba(255,255,255,.68)" stroke-width="2"/><path d="M17 32 Q20 18 34 14 H48 L45 32Z" fill="#24313a" stroke="#817866" stroke-width="1"/><path d="M50 13 H72 V31 H48Z" fill="#26353e" stroke="#817866" stroke-width="1"/><rect x="76" y="13" width="22" height="18" rx="2" fill="#26353e" stroke="#817866"/><rect x="102" y="13" width="22" height="18" rx="2" fill="#26353e" stroke="#817866"/><rect x="128" y="13" width="22" height="18" rx="2" fill="#26353e" stroke="#817866"/><path d="M154 13 H168 Q179 14 187 23 L190 31 H154Z" fill="#26353e" stroke="#817866" stroke-width="1"/><path d="M66 35 V49 M139 35 V49" stroke="#d8c9aa" stroke-width="1.2" opacity=".8"/><rect x="84" y="36" width="37" height="4" rx="2" fill="#e8dcc2" opacity=".8"/><circle cx="194" cy="37" r="2.6" fill="#f6dc80" stroke="#6c5641"/><circle cx="13" cy="39" r="1.8" fill="#c63831"/><path d="M14 50 H194" stroke="#c9b99b" stroke-width="2"/><path d="M33 51 H64 M141 51 H173" stroke="#3f4042" stroke-width="4" stroke-linecap="round"/><circle class="wfgg-micheline-wheel" cx="42" cy="55" r="8" fill="#252628" stroke="url(#wfggMichMetal)" stroke-width="3"/><circle cx="42" cy="55" r="2.2" fill="#9e9b93"/><circle class="wfgg-micheline-wheel" cx="57" cy="55" r="8" fill="#252628" stroke="url(#wfggMichMetal)" stroke-width="3"/><circle cx="57" cy="55" r="2.2" fill="#9e9b93"/><circle class="wfgg-micheline-wheel" cx="149" cy="55" r="8" fill="#252628" stroke="url(#wfggMichMetal)" stroke-width="3"/><circle cx="149" cy="55" r="2.2" fill="#9e9b93"/><circle class="wfgg-micheline-wheel" cx="164" cy="55" r="8" fill="#252628" stroke="url(#wfggMichMetal)" stroke-width="3"/><circle cx="164" cy="55" r="2.2" fill="#9e9b93"/><path d="M7 43 L2 45 M199 43 L204 45" stroke="#a9a69f" stroke-width="2" stroke-linecap="round"/></svg></div></div></div>';
'''

src, n_css = re.subn(
    r"      style\.textContent='@keyframes wfggTrainRide.*?';\n(?=      document\.head\.appendChild\(style\);)",
    lambda m: new_css,
    src,
    count=1,
    flags=re.S,
)
if n_css != 1:
    raise SystemExit(f'Expected exactly one Train loader CSS block, got {n_css}')

src, n_html = re.subn(
    r"      el\.innerHTML='<div class=\"wfgg-train-stage\".*?</div>';\n(?=      document\.documentElement\.appendChild\(el\);)",
    lambda m: new_html,
    src,
    count=1,
    flags=re.S,
)
if n_html != 1:
    raise SystemExit(f'Expected exactly one Train loader HTML block, got {n_html}')

path.write_text(src, encoding='utf-8')
