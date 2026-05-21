"""
通用评论提取引擎
读取 XML 规则文件,动态生成提取 JS 并执行,与具体站点 DOM 解耦。

Phase 2 移到 shared/ 后,XML 路径由调用方显式传入(以前的 load_engine 便利函数已移除)。
"""

import xml.etree.ElementTree as ET


class ExtractionEngine:
    """解析 XML 规则 → 生成 JS → 执行提取"""

    def __init__(self, xml_path):
        self.xml_path = xml_path
        self.rules = self._parse_xml(xml_path)

    # ==================== XML 解析 ====================

    def _parse_xml(self, path):
        tree = ET.parse(path)
        root = tree.getroot()
        return {
            'traversal': self._parse_traversal(root.find('traversal')),
            'fields': self._parse_fields(root.find('fields')),
            'scroll': self._parse_scroll(root.find('scroll')),
        }

    def _parse_traversal(self, node):
        group = node.find('group')
        return {
            'group_selector': group.get('selector'),
            'main_selector': group.find('main').get('selector'),
            'sub_selector': group.find('sub').get('selector'),
        }

    def _parse_fields(self, node):
        fields = []
        for f in node.findall('field'):
            sel_el = f.find('selector')
            src_el = f.find('source')
            trans_el = f.find('transform')

            selector = sel_el.text.strip() if sel_el is not None else None
            source_type = src_el.get('type', 'text').strip() if src_el is not None else 'text'
            source_attr = src_el.text.strip() if src_el is not None and src_el.text else None

            transform = None
            if trans_el is not None:
                ttype = trans_el.get('type', '')
                tval = trans_el.text.strip() if trans_el.text else ''
                transform = {'type': ttype, 'value': tval}

            fields.append({
                'name': f.get('name'),
                'target': f.get('target', 'main|sub'),
                'selector': selector,
                'source_type': source_type,
                'source_attr': source_attr,
                'transform': transform,
            })
        return fields

    def _parse_scroll(self, node):
        if node is None:
            return {}
        end = node.find('end_marker')
        empty = node.find('empty_marker')
        expand = node.find('expand_replies')
        container = node.find('container')
        return {
            'container_selector': container.get('selector') if container is not None else '.note-scroller',
            'expand_selector': expand.get('selector') if expand is not None else 'a',
            'expand_match': expand.get('match_text') if expand is not None else '展开+回复|条回复',
            'end_match': end.get('match_text') if end is not None else '- THE END -',
            'empty_match': empty.get('match_text') if empty is not None else '这是一片荒地|还没有评论|暂无评论',
        }

    # ==================== JS 生成 ====================

    def _build_js_function(self):
        """根据 XML 规则动态生成提取 JS"""
        t = self.rules['traversal']
        fields = self.rules['fields']

        main_fields = [f for f in fields if 'main' in f['target']]
        sub_fields = [f for f in fields if 'sub' in f['target']]

        lines = []
        lines.append("function extractItem(el, mainData) {")
        lines.append("  var e = {};")

        for f in main_fields + sub_fields:
            name = f['name']
            stype = f['source_type']
            sel = f['selector']

            if stype == 'prop:id':
                lines.append(f"  e['{name}'] = el.id || '';")
            elif stype == 'text':
                if sel:
                    safe_sel = sel.replace("'", "\\'")
                    lines.append(f"  try {{ var _n = el.querySelector('{safe_sel}'); if (_n) e['{name}'] = _n.textContent.trim(); }} catch(_) {{}}")
            elif stype == 'attr':
                if sel:
                    safe_sel = sel.replace("'", "\\'")
                    lines.append(f"  try {{ var _n = el.querySelector('{safe_sel}'); if (_n) e['{name}'] = _n.getAttribute('{f['source_attr']}') || ''; }} catch(_) {{}}")
            elif stype == 'exists':
                if sel:
                    safe_sel = sel.replace("'", "\\'")
                    lines.append(f"  if (el.querySelector('{safe_sel}')) e['{name}'] = true;")
            elif stype.startswith('parent_main:'):
                ref_field = stype.split(':', 1)[1]
                lines.append(f"  e['{name}'] = mainData['{ref_field}'] || '';")

        lines.append("  return e;")
        lines.append("}")

        lines.append("")
        lines.append("var results = [];")
        lines.append(f"var groups = document.querySelectorAll('{t['group_selector']}');")
        lines.append("for (var gi = 0; gi < groups.length; gi++) {")
        lines.append("  var g = groups[gi];")
        lines.append("  var mainData = {};")
        lines.append(f"  var mainEl = g.querySelector('{t['main_selector']}');")
        lines.append("  if (mainEl) {")
        lines.append("    mainData = extractItem(mainEl, {});")
        lines.append("    mainData['is_sub'] = false;")
        lines.append("    results.push(mainData);")
        lines.append("  }")
        lines.append(f"  var subs = g.querySelectorAll('{t['sub_selector']}');")
        lines.append("  for (var si = 0; si < subs.length; si++) {")
        lines.append("    var sub = extractItem(subs[si], mainData);")
        lines.append("    sub['is_sub'] = true;")
        lines.append("    results.push(sub);")
        lines.append("  }")
        lines.append("}")
        lines.append("window.__xhs_all = JSON.stringify(results);")
        lines.append("return results.length;")

        return "(function() {\n" + "\n".join(lines) + "\n})()"

    def get_extract_js(self):
        return self._build_js_function()

    # ==================== 滚动控制 ====================

    def get_scroll_js(self):
        s = self.rules['scroll']
        return {
            'check_empty': f"(function(){{var b=document.body.innerText||'';return /({s.get('empty_match','')})/.test(b);}})()",
            'check_end': f"(function(){{var b=document.body.innerText||'';return /({s.get('end_match','')})/.test(b);}})()",
            'expand': f"(function(){{document.querySelectorAll('{s.get('expand_selector','a')}').forEach(function(a){{var t=(a.textContent||'').trim();if(/({s.get('expand_match','')})/.test(t)&&a.offsetParent)a.click()}});}})()",
            'scroll': f"(function(){{var s=document.querySelector('{s.get('container_selector','.note-scroller')}');if(s)s.scrollTo({{top:s.scrollHeight,behavior:'smooth'}});else window.scrollBy(0,1000);}})()",
        }

    # ==================== 值转换 ====================

    def apply_transforms(self, data):
        for item in data:
            for f in self.rules['fields']:
                name = f['name']
                trans = f.get('transform')
                if not trans or name not in item:
                    continue
                val = item[name]
                if trans['type'] == 'if_eq':
                    parts = trans['value'].split(':', 1)
                    if len(parts) == 2 and str(val) == parts[0]:
                        item[name] = parts[1]
        return data
