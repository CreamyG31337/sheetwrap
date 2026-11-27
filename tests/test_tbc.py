from sheetwrap.tbc import datum_from_report

# trimmed to the structure of a TBC Project Computation Report summary
REPORT = """<html><body><table><tr><td><table>
<tr><th><B>Project File Data</B></th></tr>
<tr><td valign="top">Name:</td><td valign="top">C:\\somewhere\\project.vce</td></tr>
</table></td><td><table>
<tr><th align="left"><B>Coordinate System</B></th></tr>
<tr><td>Name:</td><td>World wide/UTM</td></tr>
<tr><td>Zone:</td><td>10 North</td></tr>
<tr><td>Datum:</td><td>NAD83(CSRS)v7-1997</td></tr>
<tr><td>Geoid:</td><td>Canada Geoid Model HT2_1997</td></tr>
<tr><td valign="top">Vertical datum:</td><td valign="top">cvd28</td></tr>
</table></td></tr></table></body></html>"""


def test_datum_from_report(tmp_path):
    p = tmp_path / "report.html"
    p.write_text(REPORT)
    assert datum_from_report(p) == "NAD83(CSRS)v7 UTM ZONE 10N / VERT: CVD28 (HT2_1997)"
