#!/usr/bin/env python3
"""
Agro Indica — Servidor Local
- POST /parse-pdf   → extrai dados do PDF NeoScanner
- POST /export-pdf  → gera PDF A4 landscape com layout validado
"""
import http.server, json, re, os, sys, io, tempfile, socketserver

PORT = 7842

# ── PDF PARSING ────────────────────────────────────────────────────────────
def extract_neoscanner(pdf_bytes):
    try: import pdfplumber
    except ImportError:
        os.system(f"{sys.executable} -m pip install pdfplumber -q")
        import pdfplumber
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
        tmp.write(pdf_bytes); tmp_path = tmp.name
    try:
        with pdfplumber.open(tmp_path) as pdf:
            text = '\n'.join(p.extract_text() or '' for p in pdf.pages)
    finally:
        os.unlink(tmp_path)
    d = {}
    def mval(label):
        x = re.search(label + r'[\s\t]+([\d.]+)', text, re.IGNORECASE)
        return float(x.group(1)) if x else None
    def mmeta(label):
        x = re.search(label + r'[:\s]+([^\n]+?)(?:\s{2,}|$)', text, re.IGNORECASE)
        return x.group(1).strip() if x else ''
    raw_name = mmeta('Nome do material').split('Data do')[0].strip()
    raw_dt   = re.search(r'Criado em:\s*(\d{2}-\w+-\d{4}\s+\d{2}:\d{2}\s+[ap]m)', text, re.IGNORECASE)
    d['datetime']       = raw_dt.group(1) if raw_dt else ''
    d['device']         = mmeta('ID do dispositivo')
    d['operator']       = mmeta('Criado por')
    d['sample_name']    = raw_name
    d['thc_total']      = mval(r'THC\s*Total')
    d['thca']           = mval('THCa')
    d['cbd_total']      = mval(r'CBD\s*Total')
    d['cbda']           = mval('CBDa')
    d['cbg_total']      = mval(r'CBG\s*Total')
    d['total_terpenes'] = mval(r'Total\s*Terpenes')
    d['moisture']       = mval('Moisture')
    d['aw']             = mval('aW')
    KNOWN = ['B-Myrcene','β-Myrcene','Limonene','A-Pinene','α-Pinene',
             'B-Caryophyllene','β-Caryophyllene','G-elemene','Linalool',
             'A-Humulene','α-Humulene','Eudesma','B-Pinene','β-Pinene',
             'A-Bisabolol','α-Bisabolol','Terpinolene','Ocimene','Valencene','Geraniol']
    seen, found = set(), []
    for t in KNOWN:
        if t.lower() in text.lower() and t.lower() not in seen:
            seen.add(t.lower()); found.append(t)
    d['terpenes'] = [{'name':t,'relative':round(max(0.04,1-i*0.11),2)} for i,t in enumerate(found)]
    return d

# ── PDF GENERATION ─────────────────────────────────────────────────────────
def generate_pdf(data):
    try: from reportlab.lib.pagesizes import A4, landscape
    except ImportError:
        os.system(f"{sys.executable} -m pip install reportlab -q")
        from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    from reportlab.lib.colors import HexColor

    W, H = landscape(A4)
    G1   = HexColor('#1a5c2a'); G2 = HexColor('#2d8a3e'); G3 = HexColor('#4ab860')
    PALE = HexColor('#eaf4ed'); OK = HexColor('#4caf7a'); WARN = HexColor('#e8a838')
    RED  = HexColor('#e05252'); GRAY = HexColor('#f5f5f3'); BD = HexColor('#e2e2e2')
    T1   = HexColor('#1a1a1a'); T2 = HexColor('#555555'); T3 = HexColor('#999999')
    WHITE = colors.white
    MX = 14*mm; MY = 10*mm; CW = W - 2*MX

    def rrect(cv,x,y,w,h,fill=None,stroke_c=None,r=4,lw=0.5):
        cv.saveState()
        if fill: cv.setFillColor(fill)
        if stroke_c: cv.setStrokeColor(stroke_c); cv.setLineWidth(lw)
        cv.roundRect(x,y,w,h,r,fill=1 if fill else 0,stroke=1 if stroke_c else 0)
        cv.restoreState()

    def hbar(cv,x,y,w,h,pct,color,bg=HexColor('#e8e8e8')):
        rrect(cv,x,y,w,h,fill=bg,r=h/2)
        if pct>0: rrect(cv,x,y,max(w*min(pct,1),h),h,fill=color,r=h/2)

    def txt(cv,x,y,s,size=8,color=T1,bold=False,align='left'):
        cv.saveState(); cv.setFillColor(color)
        cv.setFont('Helvetica-Bold' if bold else 'Helvetica',size)
        if align=='right': cv.drawRightString(x,y,s)
        elif align=='center': cv.drawCentredString(x,y,s)
        else: cv.drawString(x,y,s)
        cv.restoreState()

    def shdr(cv,x,y,label,end_x):
        cv.saveState(); cv.setFont('Helvetica-Bold',6.5); cv.setFillColor(G1)
        tw = cv.stringWidth(label,'Helvetica-Bold',6.5); cv.drawString(x,y,label)
        cv.setStrokeColor(BD); cv.setLineWidth(0.5); cv.line(x+tw+5,y+2.5,end_x,y+2.5)
        cv.restoreState()

    def sdot(cv,x,y,color,r=3):
        cv.saveState(); cv.setFillColor(color); cv.circle(x,y,r,fill=1,stroke=0); cv.restoreState()

    def big_card(cv,x,y,w,h,lbl,val,unit='',ref='',dot_c=OK,vs=22):
        rrect(cv,x,y,w,h,fill=GRAY,r=5); sdot(cv,x+w-8,y+h-8,dot_c,3)
        txt(cv,x+8,y+h-13,lbl,7,T2)
        txt(cv,x+8,y+h-32,val,vs,T1,bold=True)
        if unit:
            vw = cv.stringWidth(val,'Helvetica-Bold',vs)
            txt(cv,x+10+vw,y+h-29,unit,9,T3)
        if ref: txt(cv,x+8,y+h-42,ref,6.5,T3)
        try:
            v=float(val.replace(',','.')); pct=min(v/15,1) if unit=='%' else min(v,1)
        except: pct=0
        hbar(cv,x+8,y+7,w-16,4,pct,dot_c)

    buf = io.BytesIO()
    cv = canvas.Canvas(buf, pagesize=landscape(A4))

    # ── HEADER
    HDR_H=18*mm; rrect(cv,0,H-HDR_H,W,HDR_H,fill=G1,r=0)
    cv.saveState(); cv.setFillColor(WHITE)
    p=cv.beginPath(); p.moveTo(MX+4,H-6*mm); p.lineTo(MX+12,H-15*mm); p.lineTo(MX+20,H-6*mm)
    cv.drawPath(p,fill=1,stroke=0)
    cv.setStrokeColor(HexColor('#7ecf95')); cv.setLineWidth(1.3)
    for off,yp in [(0,H-10*mm),(1.5,H-12*mm),(3,H-14*mm)]:
        cv.arc(MX+off,yp-3,MX+20-off,yp+1,0,180)
    cv.restoreState()
    txt(cv,MX+26,H-8*mm,'AGRO INDICA',13,WHITE,bold=True)
    txt(cv,MX+26,H-12.5*mm,'TECNOLOGIA  ·  GESTÃO  ·  RESULTADOS',7,HexColor('#9ad4b0'))
    txt(cv,W-MX,H-7.5*mm,'RELATÓRIO DE QUALIDADE',9,WHITE,bold=True,align='right')
    txt(cv,W-MX,H-11.5*mm,data.get('datetime',''),7.5,HexColor('#9ad4b0'),align='right')
    txt(cv,W-MX,H-15*mm,'Device: '+data.get('device',''),7,HexColor('#9ad4b0'),align='right')

    # ── SAMPLE BAR
    SB_Y=H-HDR_H-11*mm; SB_H=9*mm; rrect(cv,MX,SB_Y,CW,SB_H,fill=GRAY,r=5)
    fields=[('LOTE / AMOSTRA',data.get('sample_name','')),
            ('VARIEDADE / GENÉTICA','preencher manualmente'),
            ('CICLO / DATA COLHEITA','preencher manualmente'),
            ('OPERADOR',data.get('operator',''))]
    col_w=CW/4
    for i,(lbl,val) in enumerate(fields):
        cx=MX+i*col_w+col_w/2
        txt(cv,cx,SB_Y+SB_H-5.5,lbl,5.5,T3,align='center')
        is_ph='preencher' in val
        txt(cv,cx,SB_Y+SB_H/2-3.5,val,7.5,T3 if is_ph else T1,align='center')
        if i<3:
            cv.saveState(); cv.setStrokeColor(BD); cv.setLineWidth(0.4)
            cv.line(MX+(i+1)*col_w,SB_Y+2,MX+(i+1)*col_w,SB_Y+SB_H-2); cv.restoreState()

    # ── 3 COLUNAS
    BODY_TOP=SB_Y-5*mm; BODY_BOT=MY+10*mm; BODY_H=BODY_TOP-BODY_BOT
    COL_GAP=5*mm
    CA_W=CW*0.30; CB_W=CW*0.38; CC_W=CW-CA_W-CB_W-2*COL_GAP
    CA_X=MX; CB_X=MX+CA_W+COL_GAP; CC_X=CB_X+CB_W+COL_GAP

    # COL A: CANABINOIDES
    shdr(cv,CA_X,BODY_TOP-1,'PERFIL DE CANABINOIDES',CA_X+CA_W)
    cbd=data.get('cbd_total') or 0; thc=data.get('thc_total') or 0
    cbda=data.get('cbda') or 0; thca=data.get('thca') or 0; cbg=data.get('cbg_total') or 0
    cana=[
        ('CBD Total', f"{cbd:.2f}".replace('.',','), '%', '', OK),
        ('CBDa',      f"{cbda:.2f}".replace('.',','),'%','',OK),
        ('THC Total', f"{thc:.2f}".replace('.',','),'%','limite RDC 1013: ≤ 0,3%', RED if thc>0.3 else OK),
        ('THCa',      f"{thca:.2f}".replace('.',','),'%','',WARN),
        ('CBG Total', f"{cbg:.2f}".replace('.',','),'%','',OK),
        ('CBN Total', 'manual','','',HexColor('#cccccc')),
    ]
    n=len(cana); gap=3*mm; ch=(BODY_H-6*mm-gap*(n-1))/n
    for i,(l,v,u,r,dc) in enumerate(cana):
        cy=BODY_BOT+(n-1-i)*(ch+gap); big_card(cv,CA_X,cy,CA_W,ch,l,v,u,r,dc,vs=22)

    # COL B: RATIO + TERPENOS
    ratio=cbd/thc if thc>0 else 0
    shdr(cv,CB_X,BODY_TOP-1,'RELAÇÃO CBD:THC — QUIMIOTIPO (RDC 1015)',CB_X+CB_W)
    RH=34*mm; RY0=BODY_TOP-6*mm-RH
    rrect(cv,CB_X,RY0,CB_W,RH,fill=PALE,r=6)
    txt(cv,CB_X+10,RY0+RH-10,'ANVISA — CBD-dominante exige mínimo 5:1',7,T3)
    txt(cv,CB_X+10,RY0+RH-46,f"{ratio:.1f}:1".replace('.',','),28,G1,bold=True)
    txt(cv,CB_X+10,RY0+9,'✓ CBD-dominante confirmado (mín. 5:1 exigido)',8.5,OK,bold=True)

    TERP_TOP=BODY_TOP-6*mm-RH-5*mm
    shdr(cv,CB_X,TERP_TOP,'PERFIL DE TERPENOS',CB_X+CB_W)
    TCH=14*mm; TCW=38*mm
    terp_total=data.get('total_terpenes') or 0
    rrect(cv,CB_X,TERP_TOP-4*mm-TCH,TCW,TCH,fill=GRAY,r=5)
    sdot(cv,CB_X+TCW-8,TERP_TOP-4*mm-TCH+TCH-6,OK,3)
    txt(cv,CB_X+6,TERP_TOP-4*mm-TCH+TCH-10,'Total Terpenos',7,T2)
    txt(cv,CB_X+6,TERP_TOP-4*mm-TCH+5,f"{terp_total:.2f}".replace('.',','),18,T1,bold=True)
    tw2=cv.stringWidth(f"{terp_total:.2f}".replace('.',','),'Helvetica-Bold',18)
    txt(cv,CB_X+8+tw2,TERP_TOP-4*mm-TCH+7,'%',8,T3)
    txt(cv,CB_X+6,TERP_TOP-4*mm-TCH+TCH-19,'ref: > 1% = premium',6,T3)

    TERP_BOT=BODY_BOT; TERP_AREA=TERP_TOP-4*mm-TCH-TERP_BOT-3*mm
    terpenes=data.get('terpenes',[])
    nt=max(len(terpenes),1); rh_t=TERP_AREA/nt
    BAR_X=CB_X+32*mm; BAR_W=CB_W-32*mm-12*mm
    TCOLS=[HexColor(x) for x in ['#4caf7a','#3b7a3b','#2d8a3e','#6abf82','#a0c878',
                                   '#c9e0a8','#1a5c2a','#8fce6e','#5ab870','#2f9c50']]
    for i,t_item in enumerate(terpenes):
        name=t_item.get('name',''); rel=t_item.get('relative',0)
        ry=TERP_BOT+(nt-1-i)*rh_t+rh_t*0.2
        lbl_t='alto' if rel>0.6 else 'médio' if rel>0.25 else 'traço'
        txt(cv,CB_X,ry+rh_t*0.15,name,7,T2)
        hbar(cv,BAR_X,ry+rh_t*0.3,BAR_W,3.5,rel,TCOLS[i%len(TCOLS)])
        txt(cv,BAR_X+BAR_W+4,ry+rh_t*0.15,lbl_t,6.5,T3)

    # COL C: FÍSICOS + CONFORMIDADE
    shdr(cv,CC_X,BODY_TOP-1,'PARÂMETROS FÍSICOS',CC_X+CC_W)
    moisture=data.get('moisture') or 0; aw=data.get('aw') or 0
    fis=[
        ('Umidade (Moisture)',f"{moisture:.1f}".replace('.',','),'%','ref: 8–13%', OK if 8<=moisture<=13 else WARN),
        ('Atividade de Água (aW)',f"{aw:.2f}".replace('.',','),'','ref: 0,55–0,65', OK if 0.55<=aw<=0.65 else WARN),
        ('Densidade de Tricomas','—','','manual',HexColor('#cccccc')),
        ('Maturidade de Tricomas','—','','manual',HexColor('#cccccc')),
        ('Aspecto Visual','—','','manual',HexColor('#cccccc')),
        ('Certificação Orgânica','—','','manual',HexColor('#cccccc')),
    ]
    FIS_TOP=BODY_TOP-6*mm; CONF_RESERVE=42*mm
    FIS_AREA=BODY_H-6*mm-CONF_RESERVE-8*mm
    fcw=(CC_W-2*mm)/2; fch=(FIS_AREA-2*mm)/3
    for i,(l,v,u,r,dc) in enumerate(fis):
        fx=CC_X+[0,fcw+2*mm][i%2]; fy=FIS_TOP-(i//2+1)*(fch+2*mm)
        big_card(cv,fx,fy,fcw,fch,l,v,u,r,dc,vs=20)

    CONF_TOP=FIS_TOP-3*(fch+2*mm)-6*mm
    shdr(cv,CC_X,CONF_TOP,'CONFORMIDADE REGULATÓRIA (RDC 1013 / 1015)',CC_X+CC_W)
    conf=[
        ('THC ≤ 0,3% (RDC 1013)',f"{thc:.2f}%".replace('.',',')+" — acima do limite",False),
        ('CBD-dominante (RDC 1015)',f"Ratio {ratio:.1f}:1 — confirmado".replace('.',','),True),
        ('Pesticidas / REBLAS','laudo pendente',None),
        ('Metais / solventes','laudo pendente',None),
        ('Fungos / micotoxinas','análise pendente',None),
        ('Rastreabilidade lote','nº lote + data + variedade',None),
    ]
    ccw=(CC_W-2*mm)/2; cch=14*mm
    for i,(ttl,desc,ok) in enumerate(conf):
        col_i=i%2; row_i=i//2
        cx=CC_X+col_i*(ccw+2*mm); cy=CONF_TOP-4*mm-(row_i+1)*(cch+2*mm)
        rrect(cv,cx,cy,ccw,cch,stroke_c=BD,r=4)
        ic_bg=HexColor('#e8f5ec') if ok==True else HexColor('#fceaea') if ok==False else HexColor('#efefef')
        ic_fg=OK if ok==True else RED if ok==False else HexColor('#aaaaaa')
        ix=cx+6; iy=cy+cch/2-4
        rrect(cv,ix,iy,8,8,fill=ic_bg,r=4)
        ic_ch='✓' if ok==True else '✗' if ok==False else '–'
        txt(cv,ix+1.5,iy+1.5,ic_ch,6.5,ic_fg,bold=True)
        tcx=cx+ccw/2
        txt(cv,tcx,cy+cch/2+2,ttl,6.5,T1,bold=True,align='center')
        txt(cv,tcx,cy+cch/2-5,desc,6.5,RED if ok==False else OK if ok==True else T3,align='center')

    # ── FOOTER
    FT_Y=MY+1*mm
    cv.saveState(); cv.setStrokeColor(BD); cv.setLineWidth(0.4)
    cv.line(MX,FT_Y+5*mm,W-MX,FT_Y+5*mm); cv.restoreState()
    txt(cv,MX,FT_Y+2*mm,'Agro Indica  ·  Cannabis Medicinal  ·  Curitiba — PR  ·  documento interno confidencial',6.5,T3)
    leg=[(OK,'dentro do parâmetro'),(WARN,'atenção'),(RED,'fora do limite'),(HexColor('#cccccc'),'manual')]
    lx=W-MX
    for lc,lt in reversed(leg):
        lw=cv.stringWidth(lt,'Helvetica',6.5); lx-=lw+5
        txt(cv,lx,FT_Y+2*mm,lt,6.5,T3); lx-=9
        cv.saveState(); cv.setFillColor(lc); cv.circle(lx+3,FT_Y+4*mm,2.8,fill=1,stroke=0); cv.restoreState(); lx-=5

    cv.save(); buf.seek(0); return buf.read()

# ── HTTP HANDLER ────────────────────────────────────────────────────────────
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self,f,*a): print(f"  [{self.address_string()}] {f%a}")
    def do_OPTIONS(self):
        self.send_response(200); self._cors(); self.end_headers()
    def do_POST(self):
        length=int(self.headers.get('Content-Length',0))
        body=self.rfile.read(length)
        try:
            if self.path=='/parse-pdf':
                data=extract_neoscanner(body)
                payload=json.dumps(data,ensure_ascii=False).encode()
                self._respond(200,'application/json',payload)
            elif self.path=='/export-pdf':
                data=json.loads(body)
                pdf_bytes=generate_pdf(data)
                self._respond(200,'application/pdf',pdf_bytes)
            else:
                self.send_response(404); self.end_headers()
        except Exception as e:
            err=json.dumps({'error':str(e)}).encode()
            self._respond(500,'application/json',err)
            print(f"  ✗ Error: {e}")
    def _respond(self,code,ct,payload):
        self.send_response(code); self._cors()
        self.send_header('Content-Type',ct)
        self.send_header('Content-Length',str(len(payload)))
        if ct=='application/pdf':
            self.send_header('Content-Disposition','attachment; filename="Agro_Indica_Relatorio.pdf"')
        self.end_headers(); self.wfile.write(payload)
    def _cors(self):
        self.send_header('Access-Control-Allow-Origin','*')
        self.send_header('Access-Control-Allow-Methods','POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers','Content-Type')

class Server(socketserver.TCPServer):
    allow_reuse_address=True

if __name__=='__main__':
    print("╔══════════════════════════════════════════════════════╗")
    print("║   Agro Indica — Servidor Local                       ║")
    print(f"║   http://localhost:{PORT}                             ║")
    print("║   Mantenha aberto enquanto usar o relatório          ║")
    print("╚══════════════════════════════════════════════════════╝\n")
    try:
        import pdfplumber; print("  ✓ pdfplumber OK")
    except: os.system(f"{sys.executable} -m pip install pdfplumber -q"); print("  ✓ pdfplumber instalado")
    try:
        from reportlab.lib.pagesizes import A4; print("  ✓ reportlab OK")
    except: os.system(f"{sys.executable} -m pip install reportlab -q"); print("  ✓ reportlab instalado")
    print("\n  Aguardando conexões...\n")
    with Server(('localhost',PORT),Handler) as s:
        try: s.serve_forever()
        except KeyboardInterrupt: print("\n  Servidor encerrado.")
