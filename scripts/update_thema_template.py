"""
One-shot helper script to patch templates/reports/thema_template.docx:

1. Insert a table row "Weitere Gewerke:" right after the "Gewerk:" row,
   guarded by docxtpl `{%tr if hat_zusatz_gewerke %} ... {%tr endif %}` tags
   so the row is hidden when no optional extra trades exist.
2. Wrap the "Verwendete Ersatzteile" block (heading, header table, for loop,
   data table, endfor) with `{%p if hat_ersatzteile %} ... {%p endif %}`
   paragraph-level conditionals, so the whole block disappears when no
   spare parts have been booked for the topic.
3. Replace Arial font with Calibri in the body document.

Idempotent: re-running is safe; already-patched structures are skipped.
"""

from __future__ import annotations

import os
import shutil
import sys
import zipfile
from copy import deepcopy

from lxml import etree


W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
XML_NS = 'http://www.w3.org/XML/1998/namespace'
W = '{%s}' % W_NS
XML = '{%s}' % XML_NS
NSMAP = {'w': W_NS}

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_PATH = os.path.join(ROOT, 'templates', 'reports', 'thema_template.docx')


def _make_run(text, font='Calibri', size_half_pt=56, bold=False, underline=False):
    r = etree.Element(W + 'r')
    rpr = etree.SubElement(r, W + 'rPr')
    rfonts = etree.SubElement(rpr, W + 'rFonts')
    rfonts.set(W + 'ascii', font)
    rfonts.set(W + 'hAnsi', font)
    rfonts.set(W + 'cs', font)
    if bold:
        etree.SubElement(rpr, W + 'b')
        etree.SubElement(rpr, W + 'bCs')
    if underline:
        u = etree.SubElement(rpr, W + 'u')
        u.set(W + 'val', 'single')
    sz = etree.SubElement(rpr, W + 'sz')
    sz.set(W + 'val', str(size_half_pt))
    szcs = etree.SubElement(rpr, W + 'szCs')
    szcs.set(W + 'val', str(size_half_pt))
    t = etree.SubElement(r, W + 't')
    t.set(XML + 'space', 'preserve')
    t.text = text
    return r


def _make_paragraph(runs, ind_left='284', jc='both'):
    p = etree.Element(W + 'p')
    ppr = etree.SubElement(p, W + 'pPr')
    if ind_left is not None:
        ind = etree.SubElement(ppr, W + 'ind')
        ind.set(W + 'left', ind_left)
    if jc is not None:
        jc_el = etree.SubElement(ppr, W + 'jc')
        jc_el.set(W + 'val', jc)
    for run in runs:
        p.append(run)
    return p


def _all_text(elem):
    return ''.join((t.text or '') for t in elem.findall('.//w:t', NSMAP))


def _replace_cell_text(cell, new_text):
    """Replace the full cell content with exactly one run carrying the text
    but reusing the formatting (rPr) of the cell's first existing run."""
    paragraphs = cell.findall('w:p', NSMAP)
    if not paragraphs:
        return
    p = paragraphs[0]
    first_run = p.find('w:r', NSMAP)
    rpr_tpl = None
    if first_run is not None:
        rpr = first_run.find('w:rPr', NSMAP)
        if rpr is not None:
            rpr_tpl = deepcopy(rpr)
    for child in list(p):
        tag = etree.QName(child).localname
        if tag in ('r', 'proofErr'):
            p.remove(child)
    new_r = etree.SubElement(p, W + 'r')
    if rpr_tpl is not None:
        new_r.append(rpr_tpl)
    t = etree.SubElement(new_r, W + 't')
    t.set(XML + 'space', 'preserve')
    t.text = new_text
    for extra_p in paragraphs[1:]:
        cell.remove(extra_p)


def update_template(path):
    if not os.path.exists(path):
        raise FileNotFoundError(path)

    with zipfile.ZipFile(path, 'r') as zin:
        names = zin.namelist()
        contents = {name: zin.read(name) for name in names}

    doc_xml = contents['word/document.xml']
    tree = etree.fromstring(doc_xml)

    # 1. Font Arial -> Calibri (body only)
    for rfonts in tree.findall('.//w:rFonts', NSMAP):
        for attr in ('ascii', 'hAnsi', 'cs'):
            key = W + attr
            if rfonts.get(key) == 'Arial':
                rfonts.set(key, 'Calibri')

    # 2. Zusatz-Gewerke row
    if 'thema_zusatz_gewerke' in _all_text(tree):
        print('Info: Zusatz-Gewerke row already present - skipping.')
    else:
        first_table = tree.find('.//w:body/w:tbl', NSMAP)
        if first_table is None:
            raise RuntimeError('First table (Bereich/Gewerk/...) not found.')
        rows = first_table.findall('w:tr', NSMAP)
        gewerk_row = None
        for row in rows:
            if 'thema_gewerk' in _all_text(row):
                gewerk_row = row
                break
        if gewerk_row is None:
            raise RuntimeError('Gewerk row not found in first table.')

        # docxtpl row-level tags: {%tr if %} and {%tr endif %} must live in
        # SEPARATE rows (the whole row carrying the tag is removed at render).
        # So we insert three rows after the Gewerk row:
        #   1) control row: {%tr if hat_zusatz_gewerke %}
        #   2) content row: "Weitere Gewerke:" | {{thema_zusatz_gewerke}}
        #   3) control row: {%tr endif %}
        row_if = deepcopy(gewerk_row)
        row_content = deepcopy(gewerk_row)
        row_endif = deepcopy(gewerk_row)

        if_cells = row_if.findall('w:tc', NSMAP)
        _replace_cell_text(if_cells[0], '{%tr if hat_zusatz_gewerke %}')
        _replace_cell_text(if_cells[1], '')

        content_cells = row_content.findall('w:tc', NSMAP)
        _replace_cell_text(content_cells[0], 'Weitere Gewerke:')
        _replace_cell_text(content_cells[1], '{{thema_zusatz_gewerke}}')

        endif_cells = row_endif.findall('w:tc', NSMAP)
        _replace_cell_text(endif_cells[0], '{%tr endif %}')
        _replace_cell_text(endif_cells[1], '')

        gewerk_row.addnext(row_endif)
        gewerk_row.addnext(row_content)
        gewerk_row.addnext(row_if)
        print('OK: 3 rows (if/content/endif) for "Weitere Gewerke" inserted.')

    # 3. Wrap Ersatzteile block
    body = tree.find('w:body', NSMAP)
    if body is None:
        raise RuntimeError('Body element not found.')

    whole_text = _all_text(tree)
    if 'hat_ersatzteile' in whole_text:
        print('Info: Ersatzteile block already wrapped - skipping.')
    else:
        body_children = list(body)
        ersatzteile_heading_idx = None
        for idx, child in enumerate(body_children):
            if etree.QName(child).localname != 'p':
                continue
            if 'Verwendete Ersatzteile' in _all_text(child):
                ersatzteile_heading_idx = idx
                break
        if ersatzteile_heading_idx is None:
            print('Warn: Ersatzteile heading not found - block unchanged.')
        else:
            ersatzteile_endfor_idx = None
            for idx in range(ersatzteile_heading_idx + 1, len(body_children)):
                child = body_children[idx]
                if etree.QName(child).localname != 'p':
                    continue
                if 'endfor' in _all_text(child):
                    ersatzteile_endfor_idx = idx
                    break
            if ersatzteile_endfor_idx is None:
                print('Warn: endfor for Ersatzteile loop not found.')
            else:
                endif_p = _make_paragraph(
                    [_make_run('{%p endif %}', size_half_pt=22)],
                    ind_left='284', jc='both',
                )
                if_p = _make_paragraph(
                    [_make_run('{%p if hat_ersatzteile %}', size_half_pt=22)],
                    ind_left='284', jc='both',
                )
                body.insert(ersatzteile_endfor_idx + 1, endif_p)
                body.insert(ersatzteile_heading_idx, if_p)
                print('OK: Ersatzteile block wrapped with hat_ersatzteile.')

    new_doc_xml = etree.tostring(
        tree, xml_declaration=True, encoding='UTF-8', standalone=True
    )
    contents['word/document.xml'] = new_doc_xml

    tmp_path = path + '.tmp'
    with zipfile.ZipFile(tmp_path, 'w', zipfile.ZIP_DEFLATED) as zout:
        for name in names:
            zout.writestr(name, contents[name])
    shutil.move(tmp_path, path)
    print('Done: ' + path)


if __name__ == '__main__':
    target = sys.argv[1] if len(sys.argv) > 1 else TEMPLATE_PATH
    update_template(target)
