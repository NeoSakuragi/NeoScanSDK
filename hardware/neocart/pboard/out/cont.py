import pcbnew, subprocess, glob, os, sys, time
O=os.path.dirname(os.path.abspath(__file__)); src=os.path.join(O,'cont_in.kicad_pcb')
JAR=glob.glob(os.path.expanduser('~/.local/share/kicad/10.0/3rdparty/plugins/app_freerouting_kicad-plugin/jar/freerouting-*.jar'))[0]
b=pcbnew.LoadBoard(src); dsn=os.path.join(O,'cont.dsn'); ses=os.path.join(O,'cont.ses')
assert pcbnew.ExportSpecctraDSN(b,dsn)
if os.path.exists(ses): os.remove(ses)
t=time.time(); r=subprocess.run(['java','-Xmx4g','-Djava.awt.headless=true','-jar',JAR,'-de',dsn,'-do',ses,'-mp','15','-us','greedy','-oit','10','-mt','4'],capture_output=True,text=True,timeout=5400)
print('rc',r.returncode,f'{time.time()-t:.0f}s'); print('\n'.join(l for l in (r.stdout+r.stderr).splitlines() if 'unrouted' in l)[-600:])
b2=pcbnew.LoadBoard(src)
# remove existing tracks so the SES (which contains every wire) is not doubled
for tr in list(b2.GetTracks()): b2.Remove(tr)
assert pcbnew.ImportSpecctraSES(b2,ses)
b2.Save(os.path.join(O,'cont_out.kicad_pcb')); print('saved cont_out')
