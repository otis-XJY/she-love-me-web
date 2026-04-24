"""
generate_html_report.py - 生成 HTML 报告

读取 stats.json + analysis.json，生成 TA回我了 内嵌报告
设计风格：剧场式关系判读报告，根据分析结果自动切换暗场/甜蜜/中性底色
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime

# Windows 控制台 UTF-8 输出
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_chart_data(stats):
    trend = stats.get("daily_trend", [])
    trend_labels = [d["date"] for d in trend[-60:]]
    trend_data = [d["count"] for d in trend[-60:]]

    hours = stats.get("active_hours", {})
    hour_labels = [f"{i}" for i in range(24)]
    hour_data = [hours.get(str(i), 0) for i in range(24)]

    basic = stats.get("basic", {})
    pie_data = [basic.get("my_messages", 0), basic.get("their_messages", 0)]

    return {
        "trend_labels": trend_labels,
        "trend_data": trend_data,
        "hour_labels": hour_labels,
        "hour_data": hour_data,
        "pie_data": pie_data,
    }


def escape_html(s):
    if not isinstance(s, str):
        s = str(s)
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def classify_report_tone(analysis, stats):
    """根据关系结论决定报告底色：positive / negative / neutral。"""
    rel = str(analysis.get("relationship_type", ""))
    label = str(analysis.get("relationship_label", ""))
    trend = str(analysis.get("relationship_trend", ""))
    text = f"{rel} {label} {trend}"
    scores = stats.get("scores", {})
    loved = scores.get("loved_index", 0)
    cold = scores.get("cold_index", 0)
    simp = scores.get("simp_index", 0)
    danger_levels = [str(item.get("level", "")) for item in analysis.get("danger_warnings", [])]

    negative_words = ("单向", "工具人", "凉", "降温", "危险", "消耗", "高危", "极高危", "不爱", "止损", "拉扯")
    positive_words = ("相互喜欢", "双向", "升温", "稳定", "平稳", "健康", "被爱", "正式确认", "关系维护")

    if any(word in text for word in negative_words) or "高危" in danger_levels or "极高危" in danger_levels:
        return "negative"
    if cold >= 55 or (simp >= 70 and loved <= 35):
        return "negative"
    if any(word in text for word in positive_words) or (loved >= 60 and cold <= 35):
        return "positive"
    return "neutral"

def render_danger_warnings(danger_warnings):
    if not danger_warnings:
        return '<p style="color:var(--text-subtle);font-size:13px;">本次鉴定未发现明显危险信号</p>'

    level_colors = {
        "极高危": ("#ef4444", "rgba(239,68,68,.12)", "rgba(239,68,68,.25)"),
        "高危":   ("#f97316", "rgba(249,115,22,.12)", "rgba(249,115,22,.25)"),
        "中危":   ("#eab308", "rgba(234,179,8,.12)",  "rgba(234,179,8,.25)"),
        "低危":   ("#22c55e", "rgba(34,197,94,.12)",  "rgba(34,197,94,.25)"),
    }

    items = []
    for w in danger_warnings:
        wtype   = escape_html(w.get("type", ""))
        level   = w.get("level", "中危")
        evidence = escape_html(w.get("evidence", ""))
        color, bg, border = level_colors.get(level, ("#6b7280", "rgba(107,114,128,.12)", "rgba(107,114,128,.25)"))
        items.append(f"""
        <div class="warning-card" style="border-color:{border};background:{bg};">
          <div class="warning-header">
            <span class="warning-type">{wtype}</span>
            <span class="warning-badge" style="color:{color};background:{bg};border-color:{border};">{level}</span>
          </div>
          <p class="warning-evidence">{evidence}</p>
        </div>""")
    return "\n".join(items)


def render_sternberg(sternberg):
    passion    = sternberg.get("passion", 0)
    intimacy   = sternberg.get("intimacy", 0)
    commitment = sternberg.get("commitment", 0)
    love_type  = escape_html(sternberg.get("love_type", ""))
    return f"""
    <div class="sternberg-wrap">
      <div class="sternberg-row">
        <span class="sternberg-label">激情</span>
        <div class="sternberg-track"><div class="sternberg-fill s-passion" style="width:{passion}%"></div></div>
        <span class="sternberg-val">{passion}</span>
      </div>
      <div class="sternberg-row">
        <span class="sternberg-label">亲密</span>
        <div class="sternberg-track"><div class="sternberg-fill s-intimacy" style="width:{intimacy}%"></div></div>
        <span class="sternberg-val">{intimacy}</span>
      </div>
      <div class="sternberg-row">
        <span class="sternberg-label">承诺</span>
        <div class="sternberg-track"><div class="sternberg-fill s-commitment" style="width:{commitment}%"></div></div>
        <span class="sternberg-val">{commitment}</span>
      </div>
      <div class="sternberg-type">→ {love_type}</div>
    </div>"""


def render_gottman(gottman):
    ratio    = gottman.get("positive_negative_ratio", 0)
    horsemen = gottman.get("horsemen_detected", [])
    risk     = escape_html(gottman.get("risk_level", ""))
    ratio_pct = min(int(ratio / 10 * 100), 100)
    repair   = gottman.get("repair_attempts", {})

    horsemen_chips = "".join(
        f'<span class="horseman-chip">{escape_html(h)}</span>' for h in horsemen
    )
    if not horsemen_chips:
        horsemen_chips = '<span style="color:var(--text-subtle);font-size:12px;">未检测到四骑士信号</span>'

    risk_color = {"高危": "#ef4444", "中危": "#eab308", "低危": "#22c55e"}.get(risk, "#6b7280")

    repair_html = ""
    if repair:
        who   = escape_html(repair.get("who_initiates", ""))
        who_label = "你先低头" if who == "me" else ("对方先低头" if who == "them" else escape_html(who))
        method = escape_html(repair.get("method", ""))
        resp   = escape_html(repair.get("partner_response", ""))
        rate   = escape_html(repair.get("success_rate", ""))
        repair_html = f"""
      <div class="repair-section">
        <div class="repair-label">修复尝试分析</div>
        <div class="repair-grid">
          {f'<div class="repair-item"><span class="repair-key">主动低头</span><span class="repair-val">{who_label}</span></div>' if who_label else ''}
          {f'<div class="repair-item"><span class="repair-key">修复方式</span><span class="repair-val">{method}</span></div>' if method else ''}
          {f'<div class="repair-item"><span class="repair-key">对方响应</span><span class="repair-val">{resp}</span></div>' if resp else ''}
          {f'<div class="repair-item"><span class="repair-key">成功率</span><span class="repair-val">{rate}</span></div>' if rate else ''}
        </div>
      </div>"""

    return f"""
    <div class="gottman-wrap">
      <div class="gottman-ratio-row">
        <div>
          <div class="gottman-ratio-val">{ratio}<span style="font-size:.5em;font-weight:500;color:var(--text-muted)">:1</span></div>
          <div class="gottman-ratio-label">正负互动比（健康值 ≥ 5:1）</div>
        </div>
        <div class="gottman-risk-badge" style="color:{risk_color};border-color:{risk_color}22;background:{risk_color}11;">{risk}</div>
      </div>
      <div class="gottman-bar-track"><div class="gottman-bar-fill" style="width:{ratio_pct}%;background:{risk_color};"></div></div>
      <div class="gottman-horsemen-label">四骑士检测</div>
      <div class="gottman-horsemen">{horsemen_chips}</div>
      {repair_html}
    </div>"""


def render_personality(personality, contact_name):
    user_att    = escape_html(personality.get("user_attachment", ""))
    partner_att = escape_html(personality.get("partner_attachment", ""))
    user_comm   = escape_html(personality.get("user_communication", ""))
    partner_comm = escape_html(personality.get("partner_communication", ""))
    user_lang   = escape_html(personality.get("user_love_language", ""))
    partner_lang = escape_html(personality.get("partner_love_language", ""))
    pursue_dist = personality.get("pursue_distance_cycle", False)
    lang_mismatch = personality.get("love_language_mismatch", False)

    pursue_html = ""
    if pursue_dist:
        loop = personality.get("pursue_distance_loop", {})
        loop_html = ""
        if loop:
            trigger = escape_html(loop.get("trigger", ""))
            retreat = escape_html(loop.get("retreat", ""))
            escalation = escape_html(loop.get("escalation", ""))
            deterioration = escape_html(loop.get("deterioration", ""))
            loop_html = f"""
        <div class="loop-steps">
          {f'<div class="loop-step"><span class="loop-num">1</span><span class="loop-text">触发：{trigger}</span></div>' if trigger else ''}
          {f'<div class="loop-step"><span class="loop-num">2</span><span class="loop-text">撤退：{retreat}</span></div>' if retreat else ''}
          {f'<div class="loop-step"><span class="loop-num">3</span><span class="loop-text">升级：{escalation}</span></div>' if escalation else ''}
          {f'<div class="loop-step"><span class="loop-num">4</span><span class="loop-text">恶化：{deterioration}</span></div>' if deterioration else ''}
        </div>"""
        pursue_html = f"""
      <div class="pursue-alert">
        <strong>追逃循环已形成</strong>：你越追，TA越逃；TA越逃，你越焦虑，负向循环持续强化。
        {loop_html}
      </div>"""

    # 情感可得性
    ea = personality.get("emotional_availability", {})
    ea_html = ""
    if ea:
        ea_level = ea.get("level", "")
        ea_evidence = escape_html(ea.get("evidence", ""))
        ea_risk = escape_html(ea.get("risk_note", ""))
        ea_color = {"高": "#22c55e", "中": "#eab308", "低": "#ef4444"}.get(ea_level, "#6b7280")
        ea_html = f"""
      <div class="ea-card">
        <div class="ea-header">
          <span class="ea-label">情感可得性评估</span>
          <span class="ea-badge" style="color:{ea_color};border-color:{ea_color}33;background:{ea_color}11;">{ea_level}</span>
        </div>
        {f'<p class="ea-evidence">{ea_evidence}</p>' if ea_evidence else ''}
        {f'<p class="ea-risk">{ea_risk}</p>' if ea_risk else ''}
      </div>"""

    lang_mismatch_html = ""
    if lang_mismatch:
        lang_mismatch_html = """
      <div class="lang-mismatch-alert">
        <strong>爱的语言不匹配</strong>：你们表达爱的方式不同，导致给予了但对方感受不到。
      </div>"""

    return f"""
    <div class="personality-table">
      <div class="pt-row pt-header">
        <div class="pt-cell"></div>
        <div class="pt-cell pt-you">你</div>
        <div class="pt-cell pt-them">{escape_html(contact_name)}</div>
      </div>
      <div class="pt-row">
        <div class="pt-cell pt-label">依恋类型</div>
        <div class="pt-cell">{user_att}</div>
        <div class="pt-cell">{partner_att}</div>
      </div>
      <div class="pt-row">
        <div class="pt-cell pt-label">沟通风格</div>
        <div class="pt-cell">{user_comm}</div>
        <div class="pt-cell">{partner_comm}</div>
      </div>
      <div class="pt-row">
        <div class="pt-cell pt-label">爱的语言</div>
        <div class="pt-cell">{user_lang}</div>
        <div class="pt-cell">{partner_lang}</div>
      </div>
    </div>
    {pursue_html}
    {ea_html}
    {lang_mismatch_html}"""


def render_strategist(strategist):
    core    = escape_html(strategist.get("core_problem", ""))
    stops   = strategist.get("stop_doing", [])
    starts  = strategist.get("start_doing", [])
    roadmap = escape_html(strategist.get("roadmap", ""))
    walkaway = strategist.get("walkaway_point", {})

    def render_stop_item(s):
        if isinstance(s, dict):
            action = escape_html(s.get("action", ""))
            reason = escape_html(s.get("reason", ""))
            quote  = escape_html(s.get("quote", ""))
            html   = f'<li class="strategy-stop-item"><span class="item-mark">停止</span>{action}'
            if reason:
                html += f'<div class="strategy-reason">{reason}</div>'
            if quote:
                html += f'<div class="strategy-quote">「{quote}」</div>'
            return html + '</li>'
        return f'<li class="strategy-stop-item"><span class="item-mark">停止</span>{escape_html(str(s))}</li>'

    def render_start_item(s):
        if isinstance(s, dict):
            action = escape_html(s.get("action", ""))
            timing = escape_html(s.get("timing", ""))
            reason = escape_html(s.get("reason", ""))
            script = escape_html(s.get("script", ""))
            html   = f'<li class="strategy-start-item"><span class="item-mark">开始</span>{action}'
            if timing:
                html += f'<div class="strategy-timing">时机：{timing}</div>'
            if reason:
                html += f'<div class="strategy-reason">{reason}</div>'
            if script:
                html += f'<div class="strategy-script">参考话术：「{script}」</div>'
            return html + '</li>'
        return f'<li class="strategy-start-item"><span class="item-mark">开始</span>{escape_html(str(s))}</li>'

    stops_html  = "\n".join(render_stop_item(s) for s in stops)
    starts_html = "\n".join(render_start_item(s) for s in starts)

    walkaway_html = ""
    if walkaway:
        wa_tf      = escape_html(walkaway.get("timeframe", ""))
        wa_trigger = escape_html(walkaway.get("trigger", ""))
        wa_reason  = escape_html(walkaway.get("reason", ""))
        walkaway_html = f"""
      <div class="walkaway-card">
        <div class="walkaway-label">止损红线</div>
        {f'<p class="walkaway-trigger">如果在 <strong>{wa_tf}</strong> 内，对方仍然出现：{wa_trigger}</p>' if wa_trigger else ''}
        {f'<p class="walkaway-reason">{wa_reason}</p>' if wa_reason else ''}
      </div>"""

    return f"""
    <div class="strategist-wrap">
      <div class="core-problem-card">
        <div class="core-problem-label">核心问题</div>
        <p class="core-problem-text">{core}</p>
      </div>
      <div class="strategy-grid">
        <div class="strategy-col">
          <div class="strategy-col-title stop-title">立即停止</div>
          <ul class="strategy-list">{stops_html}</ul>
        </div>
        <div class="strategy-col">
          <div class="strategy-col-title start-title">立即开始</div>
          <ul class="strategy-list">{starts_html}</ul>
        </div>
      </div>
      <div class="roadmap-card">
        <div class="roadmap-label">推进路线图</div>
        <p class="roadmap-text">{roadmap}</p>
      </div>
      {walkaway_html}
    </div>"""


def render_key_findings(key_findings):
    if not key_findings:
        return '<p style="color:var(--text-subtle);font-size:13px;">暂无鉴定发现</p>'

    items = []
    for i, f in enumerate(key_findings):
        title    = escape_html(f.get("title", f"发现{i+1}"))
        quote    = escape_html(f.get("quote", ""))
        analysis = escape_html(f.get("analysis", ""))
        items.append(f"""
        <div class="finding-card">
          <div class="finding-index">{i+1:02d}</div>
          <div class="finding-body">
            <div class="finding-title">{title}</div>
            {f'<blockquote class="finding-quote">「{quote}」</blockquote>' if quote else ''}
            <p class="finding-analysis">{analysis}</p>
          </div>
        </div>""")
    return "\n".join(items)


def render_relationship_stage(rel_stage):
    """渲染关系阶段时间线"""
    if not rel_stage:
        return ""
    stage       = rel_stage.get("stage", "")
    description = escape_html(rel_stage.get("stage_description", ""))
    is_situ     = rel_stage.get("is_situationship", False)
    situ_ev     = escape_html(rel_stage.get("situationship_evidence", ""))
    stage_risk  = escape_html(rel_stage.get("stage_risk", ""))
    adv_path    = escape_html(rel_stage.get("advancement_path", ""))

    stages = ["初识试探期", "暧昧升温期", "拉锯确认期", "实名化前夜", "正式确认期", "关系维护期", "降温衰退期"]
    current_idx = stages.index(stage) if stage in stages else -1

    nodes_html = ""
    for i, s in enumerate(stages):
        is_current = (i == current_idx)
        cls = "stage-node active" if is_current else "stage-node"
        label_cls = "stage-label active-label" if is_current else "stage-label"
        nodes_html += f'<div class="{cls}"><div class="stage-dot"></div><div class="{label_cls}">{escape_html(s)}</div></div>'

    situ_badge = ""
    if is_situ:
        situ_badge = f"""
      <div class="situ-badge">
        <span>实名化前夜</span> · 除了一个名分，其余情侣待遇你们都有了
      </div>
      {f'<p class="stage-evidence">证据：{situ_ev}</p>' if situ_ev else ''}"""

    risk_html = f'<div class="stage-risk-row"><span class="stage-risk-label">当前风险</span> <span class="stage-risk-text">{stage_risk}</span></div>' if stage_risk else ""
    adv_html  = f'<div class="stage-adv-row"><span class="stage-adv-label">推进方向</span> <span class="stage-adv-text">{adv_path}</span></div>' if adv_path else ""

    return f"""
    <div class="stage-wrap">
      <div class="stage-timeline">{nodes_html}</div>
      {situ_badge}
      <div class="stage-desc">{description}</div>
      {risk_html}
      {adv_html}
    </div>"""


def render_emotional_asymmetry(asym):
    """渲染情感不对称分析"""
    if not asym:
        return ""
    score       = asym.get("symmetry_score", 5)
    anchor      = asym.get("anchor_person", "me")
    anchor_desc = escape_html(asym.get("anchor_description", ""))
    conflict    = escape_html(asym.get("conflict_pattern", ""))
    power_dyn   = escape_html(asym.get("power_dynamics", ""))
    turning     = asym.get("key_turning_point", {})

    score_pct = int(score / 10 * 100)
    anchor_label = "你" if anchor == "me" else "对方"
    float_label  = "对方" if anchor == "me" else "你"

    score_color = "#a855f7" if score >= 7 else ("#eab308" if score >= 4 else "#ef4444")

    turning_html = ""
    if turning and turning.get("date"):
        t_date  = escape_html(turning.get("date", ""))
        t_event = escape_html(turning.get("event", ""))
        turning_html = f"""
      <div class="asym-turning">
        <span class="asym-turning-label">关键转折点</span>
        <span class="asym-turning-date">{t_date}</span>
        <p class="asym-turning-event">{t_event}</p>
      </div>"""

    power_html = f'<div class="asym-power"><span class="asym-power-label">权力动态</span> {power_dyn}</div>' if power_dyn else ""

    return f"""
    <div class="asym-wrap">
      <div class="asym-score-row">
        <div class="asym-score-info">
          <div class="asym-score-val" style="color:{score_color}">{score}<span style="font-size:.5em;font-weight:500;color:var(--text-muted)">/10</span></div>
          <div class="asym-score-label">情感对称性</div>
        </div>
        <div class="asym-roles">
          <span class="asym-role anchor-role">{anchor_label} = 锚</span>
          <span class="asym-role float-role">{float_label} = 浮标</span>
        </div>
      </div>
      <div class="asym-bar-track"><div class="asym-bar-fill" style="width:{score_pct}%;background:{score_color};"></div></div>
      {f'<p class="asym-anchor-desc">{anchor_desc}</p>' if anchor_desc else ''}
      {f'<div class="asym-conflict"><span class="asym-conflict-label">冲突模式</span> {conflict}</div>' if conflict else ''}
      {power_html}
      {turning_html}
    </div>"""


def render_personality_portrait(portrait, contact_name):
    """渲染人格深度画像"""
    if not portrait:
        return ""

    def render_person(person_data, label):
        if not person_data:
            return ""
        core_traits = person_data.get("core_traits", [])
        core_needs  = escape_html(person_data.get("core_needs", ""))
        defenses    = person_data.get("defense_mechanisms", [])
        b5          = person_data.get("big_five_sketch", {})
        trust       = escape_html(person_data.get("trust_architecture", ""))

        traits_html = "".join(f'<span class="trait-chip">{escape_html(t)}</span>' for t in core_traits)

        defenses_html = ""
        for d in defenses:
            dtype   = escape_html(d.get("type", ""))
            trigger = escape_html(d.get("trigger", ""))
            evidence= escape_html(d.get("evidence", ""))
            meaning = escape_html(d.get("real_meaning", ""))
            defenses_html += f"""
          <div class="defense-item">
            <div class="defense-type">{dtype}</div>
            <div class="defense-detail">触发：{trigger}</div>
            {f'<div class="defense-quote">「{evidence}」</div>' if evidence else ''}
            {f'<div class="defense-meaning">真实含义：{meaning}</div>' if meaning else ''}
          </div>"""

        b5_html = ""
        if b5:
            b5_map = {
                "conscientiousness": "尽责性",
                "neuroticism": "神经质",
                "agreeableness": "亲和力",
                "openness": "开放性",
                "extraversion": "外向性"
            }
            b5_rows = ""
            for key, label_cn in b5_map.items():
                val = escape_html(b5.get(key, ""))
                if val:
                    level = val.split(" ")[0] if " " in val or "—" in val else val[:1]
                    level_color = {"高": "#a855f7", "中": "#6b7280", "低": "#3b82f6"}.get(level, "#6b7280")
                    b5_rows += f'<div class="b5-row"><span class="b5-label">{label_cn}</span><span class="b5-val" style="color:{level_color}">{val}</span></div>'
            b5_html = f'<div class="b5-section">{b5_rows}</div>'

        return f"""
        <div class="portrait-person">
          <div class="portrait-person-title">{label}</div>
          <div class="portrait-traits">{traits_html}</div>
          {f'<div class="portrait-needs"><span class="needs-label">底层需求</span> {core_needs}</div>' if core_needs else ''}
          {f'<div class="portrait-defenses-title">防御机制</div>{defenses_html}' if defenses_html else ''}
          {b5_html}
          {f'<div class="portrait-trust"><span class="trust-label">信任架构</span> {trust}</div>' if trust else ''}
        </div>"""

    # 需求-行为解码
    needs_map_html = ""
    user_data    = portrait.get("user", {})
    partner_data = portrait.get("partner", {})
    partner_needs_map = partner_data.get("needs_behavior_map", [])
    if partner_needs_map:
        items = ""
        for m in partner_needs_map:
            behavior = escape_html(m.get("behavior", ""))
            need     = escape_html(m.get("need", ""))
            decode   = escape_html(m.get("decode", ""))
            items += f"""
        <div class="nbm-item">
          <div class="nbm-behavior">「{behavior}」</div>
          <div class="nbm-arrow">↓</div>
          <div class="nbm-need">{need}</div>
          {f'<div class="nbm-decode">{decode}</div>' if decode else ''}
        </div>"""
        needs_map_html = f'<div class="nbm-section"><div class="nbm-title">行为解码：对方真正想要的是什么</div><div class="nbm-list">{items}</div></div>'

    user_html    = render_person(user_data, "你")
    partner_html = render_person(partner_data, escape_html(contact_name))

    return f"""
    <div class="portrait-grid">
      {user_html}
      {partner_html}
    </div>
    {needs_map_html}"""


def render_language_patterns(lang_patterns, linguistic_stats, contact_name):
    """渲染语言模式分析"""
    if not lang_patterns:
        return ""
    hedging      = escape_html(lang_patterns.get("hedging_density", ""))
    future_ori   = escape_html(lang_patterns.get("future_orientation", ""))
    valence      = escape_html(lang_patterns.get("emotional_valence_ratio", ""))
    conditional  = escape_html(lang_patterns.get("conditional_density", ""))
    key_finding  = escape_html(lang_patterns.get("key_linguistic_finding", ""))

    density_color = {"高": "#ef4444", "中": "#eab308", "低": "#22c55e"}

    hedging_color     = density_color.get(hedging.split(" ")[0] if hedging else "", "#6b7280")
    conditional_color = density_color.get(conditional.split(" ")[0] if conditional else "", "#6b7280")

    future_color = {"真实期待": "#22c55e", "虚假承诺": "#ef4444", "中性": "#6b7280"}.get(future_ori, "#6b7280")

    # 从统计数据补充数值
    we_me    = linguistic_stats.get("pronoun_we_count", {}).get("me", 0)
    we_them  = linguistic_stats.get("pronoun_we_count", {}).get("them", 0)
    rev_me   = linguistic_stats.get("revoke_count", {}).get("me", 0)
    rev_them = linguistic_stats.get("revoke_count", {}).get("them", 0)

    return f"""
    <div class="lang-wrap">
      <div class="lang-cards">
        <div class="lang-card">
          <div class="lang-card-label">模糊词密度</div>
          <div class="lang-card-val" style="color:{hedging_color}">{hedging or "—"}</div>
          <div class="lang-card-sub">也许/可能/感觉/好像</div>
        </div>
        <div class="lang-card">
          <div class="lang-card-label">条件句密度</div>
          <div class="lang-card-val" style="color:{conditional_color}">{conditional or "—"}</div>
          <div class="lang-card-sub">如果/要是/假如</div>
        </div>
        <div class="lang-card">
          <div class="lang-card-label">未来指向</div>
          <div class="lang-card-val" style="color:{future_color};font-size:14px">{future_ori or "—"}</div>
          <div class="lang-card-sub">以后/将来/等你</div>
        </div>
        <div class="lang-card">
          <div class="lang-card-label">情绪正负比</div>
          <div class="lang-card-val" style="font-size:13px">{valence or "—"}</div>
          <div class="lang-card-sub">正向 vs 负向情绪词</div>
        </div>
      </div>
      <div class="lang-stats-row">
        <span class="lang-stat-item">「我们」：你 {we_me} 次 / 对方 {we_them} 次</span>
        <span class="lang-stat-sep">·</span>
        <span class="lang-stat-item">撤回消息：你 {rev_me} 次 / 对方 {rev_them} 次</span>
      </div>
      {f'<div class="lang-finding"><span class="lang-finding-label">语言洞察</span><p>{key_finding}</p></div>' if key_finding else ''}
    </div>"""


def render_html(stats, analysis, contact_name):
    scores = stats.get("scores", {})
    basic = stats.get("basic", {})
    initiative = stats.get("initiative", {})
    reply = stats.get("reply_speed", {})
    bombing = stats.get("bombing", {})
    goodnight = stats.get("goodnight", {})
    msg_len = stats.get("message_length", {})

    def value_or(value, default=0):
        return default if value is None else value

    def pct(value):
        try:
            return max(0, min(100, int(value)))
        except Exception:
            return 0

    def text(value, fallback="未判断"):
        value = fallback if value in (None, "") else value
        return escape_html(value)

    def plain_list(items, empty="暂无明确结论"):
        if not items:
            return f'<p class="ta-empty">{escape_html(empty)}</p>'
        return "".join(f'<span class="ta-chip">{escape_html(item)}</span>' for item in items)

    def render_findings(items):
        if not items:
            return '<p class="ta-empty">暂无鉴定发现。</p>'
        blocks = []
        for index, item in enumerate(items[:6], 1):
            if isinstance(item, dict):
                title = text(item.get("title", f"发现 {index}"))
                quote = text(item.get("quote", ""), "")
                analysis_text = text(item.get("analysis", ""), "")
            else:
                title = f"发现 {index}"
                quote = ""
                analysis_text = text(item)
            blocks.append(f'''
        <div class="ta-evidence-item">
          <b>{index:02d}</b>
          <div>
            <h4>{title}</h4>
            {f'<blockquote>{quote}</blockquote>' if quote else ''}
            <p>{analysis_text}</p>
          </div>
        </div>''')
        return "".join(blocks)

    def render_warnings(items):
        if not items:
            return '<p class="ta-empty">本次没有明显风险信号。</p>'
        blocks = []
        for item in items[:5]:
            level = text(item.get("level", "中危"))
            wtype = text(item.get("type", "风险信号"))
            evidence = text(item.get("evidence", ""), "")
            blocks.append(f'''
        <div class="ta-warning">
          <div><strong>{wtype}</strong><span>{level}</span></div>
          {f'<p>{evidence}</p>' if evidence else ''}
        </div>''')
        return "".join(blocks)

    def render_stage(stage):
        if not stage:
            return '<p class="ta-empty">暂无关系阶段判断。</p>'
        title = text(stage.get("stage", "未定位"))
        desc = text(stage.get("stage_description", ""), "")
        risk = text(stage.get("stage_risk", ""), "")
        path_text = text(stage.get("advancement_path", ""), "")
        situ = bool(stage.get("is_situationship"))
        situ_ev = text(stage.get("situationship_evidence", ""), "")
        status_line = f"实名化前夜：{situ_ev}" if situ else "未检测到明显悬空关系标记。"
        return f'''
        <div class="ta-stage-card">
          <div class="ta-stage-main"><span>当前阶段</span><strong>{title}</strong></div>
          {f'<p>{desc}</p>' if desc else ''}
          <p><b>关系状态</b>{status_line}</p>
          {f'<p><b>当前风险</b>{risk}</p>' if risk else ''}
          {f'<p><b>推进方向</b>{path_text}</p>' if path_text else ''}
        </div>'''

    def render_love_model(sternberg, gottman):
        passion = pct(sternberg.get("passion", 0))
        intimacy = pct(sternberg.get("intimacy", 0))
        commitment = pct(sternberg.get("commitment", 0))
        love_type = text(sternberg.get("love_type", "未判断"))
        ratio = value_or(gottman.get("positive_negative_ratio", 0), 0)
        risk = text(gottman.get("risk_level", "未判断"))
        horsemen = gottman.get("horsemen_detected", []) or []
        repair = gottman.get("repair_attempts", {}) or {}
        repair_parts = [repair.get("method"), repair.get("partner_response"), repair.get("success_rate")]
        repair_text = "；".join(text(part, "") for part in repair_parts if part)
        bars = [("激情", passion), ("亲密", intimacy), ("承诺", commitment)]
        bars_html = "".join(f'''
          <div class="ta-model-row"><span>{label}</span><i><em style="width:{val}%"></em></i><b>{val}</b></div>''' for label, val in bars)
        return f'''
        <div class="ta-panel ta-model-panel">
          <h3>爱情三角</h3>
          {bars_html}
          <p class="ta-model-note">类型判断：{love_type}</p>
        </div>
        <div class="ta-panel ta-model-panel">
          <h3>关系健康度</h3>
          <div class="ta-ratio"><strong>{ratio}</strong><span>正负互动比</span></div>
          <p class="ta-model-note">风险级别：{risk}</p>
          <div class="ta-chip-row">{plain_list(horsemen, "未检测到四骑士信号")}</div>
          {f'<p class="ta-model-note">修复线索：{repair_text}</p>' if repair_text else ''}
        </div>'''

    def render_personality_block(personality, portrait):
        rows = [
            ("依恋类型", personality.get("user_attachment"), personality.get("partner_attachment")),
            ("沟通风格", personality.get("user_communication"), personality.get("partner_communication")),
            ("爱的语言", personality.get("user_love_language"), personality.get("partner_love_language")),
        ]
        row_html = "".join(f'''
          <div class="ta-person-row"><span>{label}</span><b>{text(me)}</b><b>{text(them)}</b></div>''' for label, me, them in rows)
        user = portrait.get("user", {}) if isinstance(portrait, dict) else {}
        partner = portrait.get("partner", {}) if isinstance(portrait, dict) else {}
        return f'''
        <div class="ta-panel">
          <h3>人格与依恋</h3>
          <div class="ta-person-head"><span></span><b>你</b><b>{escape_html(contact_name)}</b></div>
          {row_html}
        </div>
        <div class="ta-panel">
          <h3>人格画像</h3>
          <div class="ta-portrait-grid">
            <div><span>你的核心需求</span><p>{text(user.get("core_needs", "暂无"))}</p><div>{plain_list(user.get("core_traits", []), "暂无特征")}</div></div>
            <div><span>对方核心需求</span><p>{text(partner.get("core_needs", "暂无"))}</p><div>{plain_list(partner.get("core_traits", []), "暂无特征")}</div></div>
          </div>
        </div>'''

    def render_strategy(strategy):
        if not strategy:
            return '<p class="ta-empty">暂无行动建议。</p>'
        stop_items = strategy.get("stop_doing", []) or []
        start_items = strategy.get("start_doing", []) or []
        walkaway = strategy.get("walkaway_point", {}) or {}

        def action_list(items, label):
            if not items:
                return '<p class="ta-empty">暂无。</p>'
            html = []
            for item in items[:5]:
                if isinstance(item, dict):
                    action = text(item.get("action", ""), "")
                    reason = text(item.get("reason", ""), "")
                    timing = text(item.get("timing", ""), "")
                    script = text(item.get("script", ""), "")
                    quote = text(item.get("quote", ""), "")
                    details = "".join([
                        f'<p>{reason}</p>' if reason else '',
                        f'<p>时机：{timing}</p>' if timing else '',
                        f'<p>参考话术：{script}</p>' if script else '',
                        f'<p>参考原话：{quote}</p>' if quote else '',
                    ])
                    html.append(f'<li><b>{label}</b><span>{action}</span>{details}</li>')
                else:
                    html.append(f'<li><b>{label}</b><span>{text(item)}</span></li>')
            return "".join(html)

        walkaway_html = ""
        if walkaway:
            walkaway_html = f'''
          <div class="ta-stopline">
            <b>止损红线</b>
            <p>{text(walkaway.get("timeframe", ""), "")}</p>
            <p>{text(walkaway.get("trigger", ""), "")}</p>
            <p>{text(walkaway.get("reason", ""), "")}</p>
          </div>'''
        return f'''
        <div class="ta-panel ta-action-panel">
          <h3>核心问题</h3>
          <p>{text(strategy.get("core_problem", ""), "暂无")}</p>
        </div>
        <div class="ta-action-grid">
          <div class="ta-panel"><h3>立即停止</h3><ul class="ta-action-list">{action_list(stop_items, "停止")}</ul></div>
          <div class="ta-panel"><h3>立即开始</h3><ul class="ta-action-list">{action_list(start_items, "开始")}</ul></div>
        </div>
        <div class="ta-panel ta-action-panel">
          <h3>推进路线</h3>
          <p>{text(strategy.get("roadmap", ""), "暂无")}</p>
          {walkaway_html}
        </div>'''

    def render_language(patterns):
        if not patterns:
            return '<p class="ta-empty">暂无语言模式结论。</p>'
        items = [
            ("我们感", patterns.get("pronoun_we_ratio")),
            ("模糊表达", patterns.get("hedging_density")),
            ("未来指向", patterns.get("future_orientation")),
            ("条件表达", patterns.get("conditional_density")),
            ("情绪正负", patterns.get("emotional_valence_ratio")),
        ]
        cards = "".join(f'<div class="ta-language-card"><span>{label}</span><p>{text(val)}</p></div>' for label, val in items)
        finding = text(patterns.get("key_linguistic_finding", ""), "")
        return f'<div class="ta-language-grid">{cards}</div>{f"<p class=\"ta-language-note\">{finding}</p>" if finding else ""}'

    simp = pct(scores.get("simp_index", 0))
    loved = pct(scores.get("loved_index", 0))
    cold = pct(scores.get("cold_index", 0))
    imbalance = pct(max(0, simp - loved - 10))
    relationship_type = text(analysis.get("relationship_type", "未知"))
    relationship_label = text(analysis.get("relationship_label", ""), "")
    relationship_trend = text(analysis.get("relationship_trend", ""), "")
    verdict = text(analysis.get("verdict", ""), "")
    simp_description = text(analysis.get("simp_description", ""), "")
    love_description = text(analysis.get("love_description", ""), "")
    date_range = basic.get("date_range", ["?", "?"])
    if not isinstance(date_range, list) or len(date_range) < 2:
        date_range = ["?", "?"]
    total_days = value_or(basic.get("total_days", 1), 1)
    total_messages = value_or(basic.get("total_messages", 0), 0)
    avg_daily = value_or(basic.get("avg_daily", 0), 0)
    my_ratio = pct(float(basic.get("my_ratio", 0)) * 100)
    their_ratio = pct(float(basic.get("their_ratio", 0)) * 100)
    speed_ratio = value_or(reply.get("speed_ratio", 1), 1)
    chart_data_js = json.dumps(build_chart_data(stats), ensure_ascii=False)
    date_str = datetime.now().strftime("%Y.%m.%d")
    report_tone = classify_report_tone(analysis, stats)

    metrics = [
        ("消息占比", f"{my_ratio}%", f"你 · 对方 {their_ratio}%"),
        ("主动发起", f"{initiative.get('my_starts', 0)} 次", f"对方 {initiative.get('their_starts', 0)} 次"),
        ("你的回复速度", text(reply.get("my_avg_human", "未计算")), f"对方 {text(reply.get('their_avg_human', '未计算'))}"),
        ("回速差距", f"{speed_ratio}x", "对方比你慢这么多倍"),
        ("连续发送", f"{bombing.get('my_bomb_count', 0)} 次", f"最多连发 {bombing.get('my_max_consecutive', 0)} 条"),
        ("先说晚安", f"{goodnight.get('my_goodnight', 0)} 次", f"对方 {goodnight.get('their_goodnight', 0)} 次"),
        ("平均字数", f"{msg_len.get('my_avg_chars', 0)} 字", f"对方 {msg_len.get('their_avg_chars', 0)} 字"),
        ("日均消息", f"{avg_daily}", "条 / 天"),
    ]
    metric_cards = "".join(f'<div class="ta-stat"><span>{label}</span><strong>{main}</strong><p>{sub}</p></div>' for label, main, sub in metrics)
    score_cards = "".join([
        f'<div class="ta-score"><i>I.</i><span>主动指数</span><strong>{simp}</strong><em><b style="width:{simp}%"></b></em>{f"<p>{simp_description}</p>" if simp_description else ""}</div>',
        f'<div class="ta-score"><i>II.</i><span>被爱指数</span><strong>{loved}</strong><em><b style="width:{loved}%"></b></em>{f"<p>{love_description}</p>" if love_description else ""}</div>',
        f'<div class="ta-score"><i>III.</i><span>冷淡指数</span><strong>{cold}</strong><em><b style="width:{cold}%"></b></em></div>',
    ])
    ingredient_rows = "".join([
        f'<div><span>主动投入</span><i><b style="width:{simp}%"></b></i><strong>{simp}%</strong></div>',
        f'<div><span>被爱成分</span><i><b style="width:{loved}%"></b></i><strong>{loved}%</strong></div>',
        f'<div><span>冷淡成分</span><i><b style="width:{cold}%"></b></i><strong>{cold}%</strong></div>',
        f'<div><span>失衡成分</span><i><b style="width:{imbalance}%"></b></i><strong>{imbalance}%</strong></div>',
    ])
    total_starts = max(initiative.get("my_starts", 0) + initiative.get("their_starts", 0), 1)
    total_goodnight = max(goodnight.get("my_goodnight", 0) + goodnight.get("their_goodnight", 0), 1)
    compare_rows = "".join([
        f'<div class="ta-compare"><p><span>你 · 消息量 {my_ratio}%</span><span>{their_ratio}% · 对方</span></p><i><b style="width:{my_ratio}%"></b><em style="width:{their_ratio}%"></em></i></div>',
        f'<div class="ta-compare"><p><span>你 · 主动发起 {initiative.get("my_starts", 0)} 次</span><span>{initiative.get("their_starts", 0)} 次 · 对方</span></p><i><b style="width:{int(initiative.get("my_starts", 0) / total_starts * 100)}%"></b><em style="width:{int(initiative.get("their_starts", 0) / total_starts * 100)}%"></em></i></div>',
        f'<div class="ta-compare"><p><span>你 · 先说晚安 {goodnight.get("my_goodnight", 0)} 次</span><span>{goodnight.get("their_goodnight", 0)} 次 · 对方</span></p><i><b style="width:{int(goodnight.get("my_goodnight", 0) / total_goodnight * 100)}%"></b><em style="width:{int(goodnight.get("their_goodnight", 0) / total_goodnight * 100)}%"></em></i></div>',
    ])

    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TA回我了 · {escape_html(contact_name)}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  body,
  .report-document {{
    margin: 0;
    --ta-bg: #f5f3ee;
    --ta-bg-2: #e9e3d8;
    --ta-panel: rgba(255, 252, 247, .94);
    --ta-panel-strong: #fffdf8;
    --ta-ink: #211f1c;
    --ta-soft: #5c5750;
    --ta-muted: #8a8075;
    --ta-line: rgba(47, 42, 35, .18);
    --ta-accent: #6f6251;
    --ta-accent-strong: #2c2924;
    --ta-good: #1f8d5a;
    --ta-danger: #b64242;
    --ta-shadow: 0 18px 50px rgba(48, 41, 31, .12);
    color: var(--ta-ink);
    background: linear-gradient(135deg, var(--ta-bg), var(--ta-bg-2));
    font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", sans-serif;
  }}
  .report-document {{
    background: transparent !important;
  }}
  body.report-tone-positive,
  .report-document.report-tone-positive {{
    --ta-bg: #fff1f2; --ta-bg-2: #f3c9ce; --ta-panel: rgba(255, 248, 246, .94); --ta-panel-strong: #fffaf7;
    --ta-ink: #35151b; --ta-soft: #6f4048; --ta-muted: #9c6670; --ta-line: rgba(125, 54, 66, .2); --ta-accent: #b94f64; --ta-accent-strong: #7b2435; --ta-good: #247b5b; --ta-danger: #9f2d3f;
  }}
  body.report-tone-negative,
  .report-document.report-tone-negative {{
    --ta-bg: #11100d; --ta-bg-2: #2a2418; --ta-panel: rgba(31, 28, 22, .9); --ta-panel-strong: #19160f;
    --ta-ink: #f6eddb; --ta-soft: #d7c3a2; --ta-muted: #a99776; --ta-line: rgba(215, 177, 101, .24); --ta-accent: #c89c48; --ta-accent-strong: #f0c56d; --ta-good: #64c28f; --ta-danger: #df6b62;
  }}
  :host-context(body.ui-rose) .report-document {{ --ta-bg: #fff1f2; --ta-bg-2: #f3c9ce; --ta-panel: rgba(255, 248, 246, .94); --ta-panel-strong: #fffaf7; --ta-ink: #35151b; --ta-soft: #6f4048; --ta-muted: #9c6670; --ta-line: rgba(125, 54, 66, .2); --ta-accent: #b94f64; --ta-accent-strong: #7b2435; }}
  :host-context(body.ui-gold) .report-document {{ --ta-bg: #11100d; --ta-bg-2: #2a2418; --ta-panel: rgba(31, 28, 22, .9); --ta-panel-strong: #19160f; --ta-ink: #f6eddb; --ta-soft: #d7c3a2; --ta-muted: #a99776; --ta-line: rgba(215, 177, 101, .24); --ta-accent: #c89c48; --ta-accent-strong: #f0c56d; }}
  :host-context(body.ui-minimal) .report-document {{ --ta-bg: #f5f3ee; --ta-bg-2: #e9e3d8; --ta-panel: rgba(255, 252, 247, .94); --ta-panel-strong: #fffdf8; --ta-ink: #211f1c; --ta-soft: #5c5750; --ta-muted: #8a8075; --ta-line: rgba(47, 42, 35, .18); --ta-accent: #6f6251; --ta-accent-strong: #2c2924; }}
  * {{ box-sizing: border-box; }}
  h1, h2, h3, h4, p, dl, dd {{ margin: 0; }}
  .ta-report {{ max-width: 1120px; margin: 0 auto; padding: clamp(22px, 4vw, 46px); color: var(--ta-ink); }}
  .ta-summary {{ display: grid; grid-template-columns: minmax(0, 1fr) minmax(260px, 340px); gap: clamp(24px, 5vw, 64px); align-items: end; padding: clamp(28px, 5vw, 58px); border: 1px solid var(--ta-line); background: radial-gradient(circle at 8% 12%, color-mix(in srgb, var(--ta-accent) 18%, transparent), transparent 32%), linear-gradient(135deg, color-mix(in srgb, var(--ta-bg) 82%, transparent), color-mix(in srgb, var(--ta-bg-2) 72%, transparent)), var(--ta-panel-strong); box-shadow: var(--ta-shadow); }}
  .ta-kicker, .ta-section-title span, .ta-panel h3 {{ color: var(--ta-accent); font-weight: 800; letter-spacing: .03em; }}
  .ta-summary h1 {{ margin-top: 16px; font-size: clamp(48px, 8vw, 92px); line-height: .98; letter-spacing: -.07em; font-weight: 900; }}
  .ta-summary-lead {{ max-width: 780px; margin-top: 22px; color: var(--ta-soft); font-size: clamp(18px, 2.2vw, 24px); line-height: 1.7; }}
  .ta-facts {{ display: grid; gap: 10px; margin: 0; }}
  .ta-facts div {{ display: grid; grid-template-columns: 76px 1fr; gap: 12px; padding: 14px 0; border-bottom: 1px solid var(--ta-line); }}
  .ta-facts dt {{ color: var(--ta-muted); font-size: 13px; }}
  .ta-facts dd {{ color: var(--ta-ink); font-size: 15px; font-weight: 800; }}
  .ta-section {{ margin-top: clamp(34px, 5vw, 60px); }}
  .ta-section-title {{ display: grid; grid-template-columns: 74px 1fr; gap: 18px; align-items: start; margin-bottom: 22px; }}
  .ta-section-title span {{ font-family: Georgia, "Times New Roman", serif; font-size: 28px; font-style: italic; line-height: 1; }}
  .ta-section-title h2 {{ font-size: clamp(28px, 4vw, 48px); line-height: 1.05; letter-spacing: -.05em; }}
  .ta-section-title p {{ margin-top: 8px; color: var(--ta-soft); font-size: 16px; line-height: 1.75; }}
  .ta-stack {{ display: grid; gap: 16px; }}
  .ta-grid-2, .ta-chart-grid, .ta-action-grid, .ta-portrait-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }}
  .ta-score-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }}
  .ta-score, .ta-stat, .ta-panel, .ta-evidence-list, .ta-ingredients, .ta-compare-wrap {{ border: 1px solid var(--ta-line); background: var(--ta-panel); padding: 24px; }}
  .ta-score i {{ display: block; color: var(--ta-accent); font: italic 800 28px Georgia, serif; margin-bottom: 18px; }}
  .ta-score span, .ta-stat span, .ta-language-card span, .ta-portrait-grid span {{ color: var(--ta-muted); font-size: 13px; font-weight: 700; }}
  .ta-score strong {{ display: block; margin: 10px 0 12px; color: var(--ta-ink); font-size: 56px; line-height: 1; letter-spacing: -.05em; }}
  .ta-score p, .ta-stat p, .ta-panel p, .ta-language-note {{ color: var(--ta-soft); font-size: 14px; line-height: 1.75; }}
  .ta-score em, .ta-ingredients i, .ta-compare i, .ta-model-row i {{ display: block; height: 4px; background: color-mix(in srgb, var(--ta-muted) 22%, transparent); overflow: hidden; }}
  .ta-score em b, .ta-ingredients i b, .ta-compare i b, .ta-compare i em, .ta-model-row i em {{ display: block; height: 100%; background: linear-gradient(90deg, var(--ta-accent), var(--ta-accent-strong)); }}
  .ta-ingredients {{ display: grid; gap: 16px; }}
  .ta-ingredients div {{ display: grid; grid-template-columns: 104px 1fr 52px; gap: 14px; align-items: center; }}
  .ta-ingredients span {{ color: var(--ta-muted); font-weight: 700; font-size: 13px; }}
  .ta-ingredients strong {{ text-align: right; }}
  .ta-stat-grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; }}
  .ta-stat strong {{ display: block; margin-top: 10px; font-size: 28px; line-height: 1.15; }}
  .ta-evidence-list {{ display: grid; gap: 14px; }}
  .ta-evidence-item {{ display: grid; grid-template-columns: 56px 1fr; gap: 16px; padding-bottom: 14px; border-bottom: 1px solid var(--ta-line); }}
  .ta-evidence-item:last-child {{ border-bottom: 0; padding-bottom: 0; }}
  .ta-evidence-item b {{ color: var(--ta-accent); font-family: Georgia, serif; font-style: italic; }}
  .ta-evidence-item h4 {{ margin-bottom: 8px; font-size: 18px; }}
  .ta-evidence-item blockquote {{ margin: 0 0 10px; padding-left: 12px; border-left: 2px solid var(--ta-accent); color: var(--ta-soft); }}
  .ta-warning {{ border: 1px solid var(--ta-line); padding: 16px; margin-top: 12px; }}
  .ta-warning:first-of-type {{ margin-top: 0; }}
  .ta-warning div {{ display: flex; justify-content: space-between; gap: 14px; margin-bottom: 8px; }}
  .ta-warning span {{ color: var(--ta-danger); font-weight: 800; }}
  .ta-language-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }}
  .ta-language-card, .ta-portrait-grid > div {{ border: 1px solid var(--ta-line); padding: 14px; }}
  .ta-language-note {{ margin-top: 14px; }}
  .ta-compare-wrap {{ display: grid; gap: 20px; }}
  .ta-compare p {{ display: flex; justify-content: space-between; color: var(--ta-soft); font-size: 13px; font-weight: 700; margin-bottom: 8px; }}
  .ta-compare i {{ position: relative; height: 8px; }}
  .ta-compare i b {{ position: absolute; left: 0; top: 0; }}
  .ta-compare i em {{ position: absolute; right: 0; top: 0; background: var(--ta-accent-strong); }}
  .ta-chart-large, .ta-chart-grid .ta-panel {{ min-height: 260px; }}
  .ta-chart-wrap {{ height: 190px; position: relative; }}
  .ta-stage-main {{ display: flex; justify-content: space-between; gap: 18px; margin-bottom: 12px; }}
  .ta-stage-main span, .ta-stage-card b {{ color: var(--ta-accent); }}
  .ta-model-row {{ display: grid; grid-template-columns: 70px 1fr 40px; gap: 12px; align-items: center; margin: 14px 0; }}
  .ta-model-row span, .ta-model-row b {{ color: var(--ta-muted); font-size: 13px; }}
  .ta-model-note {{ margin-top: 12px; }}
  .ta-ratio strong {{ font-size: 48px; letter-spacing: -.05em; }}
  .ta-ratio span {{ margin-left: 12px; color: var(--ta-muted); }}
  .ta-chip-row, .ta-portrait-grid div div {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }}
  .ta-chip {{ border: 1px solid var(--ta-line); color: var(--ta-ink); padding: 5px 10px; font-size: 12px; }}
  .ta-person-head, .ta-person-row {{ display: grid; grid-template-columns: 110px 1fr 1fr; gap: 12px; padding: 12px 0; border-bottom: 1px solid var(--ta-line); }}
  .ta-person-head b, .ta-person-row b {{ font-size: 14px; }}
  .ta-person-row span {{ color: var(--ta-muted); }}
  .ta-action-list {{ list-style: none; margin: 0; padding: 0; display: grid; gap: 14px; }}
  .ta-action-list li {{ border-bottom: 1px solid var(--ta-line); padding-bottom: 14px; }}
  .ta-action-list b {{ display: inline-block; margin-right: 10px; color: var(--ta-accent); }}
  .ta-action-list span {{ font-weight: 800; }}
  .ta-stopline {{ margin-top: 18px; padding-top: 18px; border-top: 1px solid var(--ta-line); }}
  .ta-final strong {{ display: block; font-size: clamp(38px, 6vw, 68px); line-height: 1; letter-spacing: -.06em; margin: 10px 0 14px; }}
  .ta-note {{ margin-top: 42px; padding-top: 18px; border-top: 1px solid var(--ta-line); color: var(--ta-muted); font-size: 13px; line-height: 1.8; }}
  .ta-empty {{ color: var(--ta-muted); font-size: 14px; line-height: 1.8; }}
  @media (max-width: 900px) {{ .ta-summary, .ta-grid-2, .ta-chart-grid, .ta-action-grid, .ta-portrait-grid {{ grid-template-columns: 1fr; }} .ta-score-grid, .ta-stat-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} }}
  @media (max-width: 640px) {{ .ta-report {{ padding: 18px; }} .ta-summary {{ padding: 24px; }} .ta-score-grid, .ta-stat-grid, .ta-language-grid {{ grid-template-columns: 1fr; }} .ta-section-title {{ grid-template-columns: 1fr; gap: 8px; }} .ta-person-head, .ta-person-row {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body class="report-tone-{report_tone}">
<article class="ta-report">
  <section class="ta-summary">
    <div>
      <p class="ta-kicker">I. 结论</p>
      <h1>{relationship_type}</h1>
      <p class="ta-summary-lead">{relationship_label or verdict}</p>
    </div>
    <dl class="ta-facts">
      <div><dt>对象</dt><dd>{escape_html(contact_name)}</dd></div>
      <div><dt>样本</dt><dd>{total_messages:,} 条消息</dd></div>
      <div><dt>范围</dt><dd>{escape_html(date_range[0])} 至 {escape_html(date_range[1])}</dd></div>
      <div><dt>密度</dt><dd>{total_days} 天 · 平均 {avg_daily:.1f} 条/天</dd></div>
    </dl>
  </section>

  <section class="ta-section">
    <div class="ta-section-title"><span>II.</span><div><h2>核心指数</h2><p>先看关系的基本盘：谁更主动，谁更被回应，以及互动是否出现失衡。</p></div></div>
    <div class="ta-stack"><div class="ta-score-grid">{score_cards}</div><div class="ta-ingredients">{ingredient_rows}</div><div class="ta-stat-grid">{metric_cards}</div></div>
  </section>

  <section class="ta-section">
    <div class="ta-section-title"><span>III.</span><div><h2>证据与风险</h2><p>把判断落到可核查的证据、风险提示和语言模式，避免只看一句话下结论。</p></div></div>
    <div class="ta-stack"><div class="ta-evidence-list">{render_findings(analysis.get("key_findings", []))}</div><div class="ta-grid-2"><div class="ta-panel"><h3>风险提示</h3>{render_warnings(analysis.get("danger_warnings", []))}</div><div class="ta-panel"><h3>语言模式</h3>{render_language(analysis.get("language_patterns") or {})}</div></div></div>
  </section>

  <section class="ta-section">
    <div class="ta-section-title"><span>IV.</span><div><h2>互动结构</h2><p>这部分看聊天节奏、关系阶段和双方投入结构，判断关系是升温、僵持还是消耗。</p></div></div>
    <div class="ta-stack">
      <div class="ta-compare-wrap">{compare_rows}</div>
      <div class="ta-panel ta-chart-large"><h3>消息趋势</h3><div class="ta-chart-wrap"><canvas id="trendChart"></canvas></div></div>
      <div class="ta-chart-grid"><div class="ta-panel"><h3>活跃时段</h3><div class="ta-chart-wrap"><canvas id="hourChart"></canvas></div></div><div class="ta-panel"><h3>消息占比</h3><div class="ta-chart-wrap"><canvas id="pieChart"></canvas></div></div></div>
      <div class="ta-panel">{render_stage(analysis.get("relationship_stage"))}</div>
      <div class="ta-grid-2">{render_love_model(analysis.get("sternberg", {}) or {}, analysis.get("gottman", {}) or {})}</div>
    </div>
  </section>

  <section class="ta-section">
    <div class="ta-section-title"><span>V.</span><div><h2>行动建议</h2><p>最后回到可执行选择：怎么停、怎么进、什么时候撤，以及双方人格结构的约束。</p></div></div>
    <div class="ta-stack"><div class="ta-panel ta-final"><h3>最终判断</h3><strong>{relationship_type}</strong><p>{verdict or relationship_label}</p>{f'<p>趋势：{relationship_trend}</p>' if relationship_trend else ''}</div>{render_strategy(analysis.get("strategist", {}) or {})}<div class="ta-grid-2">{render_personality_block(analysis.get("personality", {}) or {}, analysis.get("personality_portrait", {}) or {})}</div></div>
  </section>

  <p class="ta-note">仅供参考 · 数据本地处理，不上传任何服务器 · TA回我了 · {date_str}</p>
</article>
<script>
const d = {chart_data_js};
const reportRoot = document.querySelector('.ta-report') || document;
const reportStyle = getComputedStyle(reportRoot);
const accent = reportStyle.getPropertyValue('--ta-accent').trim() || '#6f6251';
const accentStrong = reportStyle.getPropertyValue('--ta-accent-strong').trim() || '#2c2924';
const muted = reportStyle.getPropertyValue('--ta-muted').trim() || '#8a8075';
const line = reportStyle.getPropertyValue('--ta-line').trim() || 'rgba(47,42,35,.18)';
const panel = reportStyle.getPropertyValue('--ta-panel-strong').trim() || '#fffdf8';
const ink = reportStyle.getPropertyValue('--ta-ink').trim() || '#211f1c';
const canvas = (id) => document.getElementById(id);
const base = {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }}, tooltip: {{ backgroundColor: panel, borderColor: line, borderWidth: 1, titleColor: ink, bodyColor: muted, padding: 12 }} }} }};
if (window.Chart && canvas('trendChart')) {{
  new Chart(canvas('trendChart'), {{ type: 'line', data: {{ labels: d.trend_labels, datasets: [{{ data: d.trend_data, borderColor: accent, backgroundColor: 'rgba(111,98,81,.10)', fill: true, tension: .35, pointRadius: 0, borderWidth: 2 }}] }}, options: {{ ...base, scales: {{ x: {{ ticks: {{ color: muted, maxTicksLimit: 8, font: {{ size: 11 }} }}, grid: {{ color: line }}, border: {{ display: false }} }}, y: {{ ticks: {{ color: muted, font: {{ size: 11 }} }}, grid: {{ color: line }}, border: {{ display: false }} }} }} }} }});
  new Chart(canvas('hourChart'), {{ type: 'bar', data: {{ labels: d.hour_labels, datasets: [{{ data: d.hour_data, backgroundColor: accent, borderColor: accentStrong, borderWidth: 1 }}] }}, options: {{ ...base, scales: {{ x: {{ ticks: {{ color: muted, maxTicksLimit: 8, font: {{ size: 10 }} }}, grid: {{ display: false }}, border: {{ display: false }} }}, y: {{ ticks: {{ color: muted, font: {{ size: 10 }} }}, grid: {{ color: line }}, border: {{ display: false }} }} }} }} }});
  new Chart(canvas('pieChart'), {{ type: 'doughnut', data: {{ labels: ['你', '{escape_html(contact_name)}'], datasets: [{{ data: d.pie_data, backgroundColor: [accentStrong, accent], borderColor: [accentStrong, accent], borderWidth: 2 }}] }}, options: {{ ...base, plugins: {{ ...base.plugins, legend: {{ display: true, position: 'bottom', labels: {{ color: muted, font: {{ size: 11 }}, padding: 16, boxWidth: 10 }} }} }}, cutout: '65%' }} }});
}}
</script>
</body>
</html>'''

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stats", required=True)
    parser.add_argument("--analysis", required=True)
    parser.add_argument("--contact", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    stats = load_json(args.stats)
    analysis = load_json(args.analysis)

    html = render_html(stats, analysis, args.contact)

    os.makedirs(args.output, exist_ok=True)
    date_tag = datetime.now().strftime("%Y%m%d_%H%M")
    safe_name = re.sub(r'[^\w\-]', '_', args.contact) if args.contact else "contact"
    out_path = os.path.join(args.output, f"{safe_name}_{date_tag}.html")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[+] 报告已生成: {out_path}", file=sys.stderr)
    print(json.dumps({"status": "ok", "path": out_path}))


if __name__ == "__main__":
    main()
