# ui.py: all the pygame eye candy. iso "3d" map, flat map toggle, tabs, heatmaps, event log, etc.
# simulation.py stays dumb; this file just draws what the graph and sim already say.
import pygame, sys, threading, math, random
from graph import residential, hospital, school, industrial, powerplant, depot, empty
from simulation import Simulation

# colors (RGB tuples). yeah its a big blob at the top, thats pygame life
bg      = (4,   6,  14)
panelbg = (9,  12,  24)
pbdr    = (28,  38,  72)
txt     = (220, 228, 250)
dim     = (100, 115, 152)
good    = (50,  220, 110)
warn    = (255, 175,  45)
bad     = (255,  55,  55)
acc     = (75,  128, 255)
acc2    = (35,  210, 195)
ambcol  = (255, 215,   0)
teamcol = (0,   232, 255)
civcol  = (255,  75, 198)
rtcol   = (0,   248, 185)
roadcol = (72,  108, 168)
floodcol= (195,  40,  40)

# day palette
daybg   = (130, 185, 240)
daypanel= (200, 215, 235)

nodecols = {
    residential:(42,100,190), hospital:(210,42,70),   school:(230,180,30),
    industrial:(145,82,30),   powerplant:(188,108,218),depot:(35,190,105),
    empty:(22,28,46),
}
riskcols = {"High":(210,20,20),"Medium":(210,190,0),"Low":(0,170,60)}

# 3D building face colors  top / left / right
bld3d = {
    hospital:    ((215,45,75),   (155,30,55),  (185,38,65)),
    school:      ((235,185,35),  (175,135,25), (205,160,30)),
    industrial:  ((150,88,35),   (100,58,20),  (125,73,27)),
    powerplant:  ((195,115,220), (140,80,160), (165,97,190)),
    depot:       ((40,195,110),  (25,140,78),  (32,168,94)),
    empty:       ((18,24,38),    (12,16,28),   (15,20,33)),
}
RESPAL = [
    ((65,120,215),(40,80,155),(52,100,185)),
    ((80,175,200),(50,120,145),(65,148,172)),
    ((160,95,220),(110,62,160),(135,78,190)),
]

# day color overrides
bldDay = {
    hospital:    ((240,80,110),  (185,55,80),  (215,68,95)),
    school:      ((255,215,60),  (200,160,35), (230,188,48)),
    industrial:  ((180,120,60),  (130,80,35),  (155,100,47)),
    powerplant:  ((220,140,250), (165,100,190),(192,120,220)),
    depot:       ((60,220,130),  (38,165,95),  (50,193,112)),
    empty:       ((160,175,140), (130,148,108),(145,162,124)),
}

# building heights by kind
bldh = {hospital:5, school:3, industrial:2, powerplant:4, depot:2, residential:1, empty:0}

TABS     = ["Layout","Roads","Ambulance","Routing","Crime"]
SPEEDS   = [1500,900,450,150]
SPDLBLS  = ["Slow","Normal","Fast","Turbo"]

# ISO constants (these are the BASE values; actual scaled by camera.scale)
ISO_W0 = 52
ISO_H0 = 28
FH0    = 14   # floor height

# little visual fluff when roads flood / rescues happen
class Ripple:
    def __init__(self,x,y): self.x=x; self.y=y; self.life=1.0
    def update(self,dt): self.life=max(0.0,self.life-dt*1.4)
    def draw(self,surf):
        for i in range(3):
            p=(1.0-self.life)+i*0.18
            if not 0<p<1: continue
            r=int(p*38); a=int((1-p)*160)
            s=pygame.Surface((r*2+2,r*2+2),pygame.SRCALPHA)
            pygame.draw.circle(s,(200,50,50,a),(r+1,r+1),r,2); surf.blit(s,(self.x-r-1,self.y-r-1))

class RescuePing:
    def __init__(self,x,y): self.x=x; self.y=y; self.life=1.0
    def update(self,dt): self.life=max(0.0,self.life-dt*1.25)
    def draw(self,surf):
        p=1.0-self.life; r=int(p*46); a=int(self.life*210)
        s=pygame.Surface((r*2+4,r*2+4),pygame.SRCALPHA)
        pygame.draw.circle(s,(255,255,255,a),(r+2,r+2),r,3); surf.blit(s,(self.x-r-2,self.y-r-2))

class Sparkle:
    def __init__(self,cx,cy):
        ang=random.uniform(0,math.pi*2); spd=random.uniform(50,160)
        self.x=float(cx); self.y=float(cy)
        self.vx=math.cos(ang)*spd; self.vy=math.sin(ang)*spd-random.uniform(20,70)
        self.life=random.uniform(0.7,2.0); self.maxl=self.life
        self.col=random.choice([ambcol,teamcol,good,(255,255,255),acc])
    def update(self,dt):
        self.x+=self.vx*dt; self.y+=self.vy*dt; self.vy+=65*dt; self.life=max(0.0,self.life-dt)
    def draw(self,surf):
        if self.life<=0: return
        a=int(255*(self.life/self.maxl)); r=max(1,int(3*self.life/self.maxl))
        s=pygame.Surface((r*2,r*2),pygame.SRCALPHA)
        pygame.draw.circle(s,(*self.col,a),(r,r),r); surf.blit(s,(int(self.x)-r,int(self.y)-r))

# pan + zoom for iso view
class Camera:
    def __init__(self):
        self.ox=640; self.oy=200; self.scale=1.0
        self.dragging=False; self.lastmx=0; self.lastmy=0

    @property
    def ISO_W(self): return ISO_W0*self.scale
    @property
    def ISO_H(self): return ISO_H0*self.scale
    @property
    def FH(self): return FH0*self.scale

    def g2s(self,row,col,height=0):
        sx=self.ox+(col-row)*(self.ISO_W*0.5)
        sy=self.oy+(col+row)*(self.ISO_H*0.5)-height*self.FH
        return int(sx),int(sy)

    def tile_diamond(self,row,col):
        hw=self.ISO_W*0.5; hh=self.ISO_H*0.5
        cx,cy=self.ox+(col-row)*hw, self.oy+(col+row)*hh
        return [(cx,cy),(cx+hw,cy+hh),(cx,cy+2*hh),(cx-hw,cy+hh)]

    def fit(self,rows,cols,areaW,areaH,ax,ay):
        # scale so city fits inside area
        fitW=areaW/(cols*ISO_W0); fitH=areaH/(rows*ISO_H0)
        self.scale=max(0.4,min(fitW,fitH,2.0))*0.7
        self.ox=ax+areaW//2; self.oy=ay+int(rows*self.ISO_H*0.5*0.1)+40

class CityMindUI:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("CityMind | Urban Intelligence System")
        self.W=1280; self.H=780
        self.screen=pygame.display.set_mode((self.W,self.H),pygame.RESIZABLE)
        try:
            self.fnsm=pygame.font.SysFont("Consolas",12)
            self.fnmd=pygame.font.SysFont("Consolas",14)
            self.fnlg=pygame.font.SysFont("Consolas",16,bold=True)
            self.fnxl=pygame.font.SysFont("Arial",26,bold=True)
            self.fnttl=pygame.font.SysFont("Arial",54,bold=True)
        except:
            self.fnsm=pygame.font.Font(None,17); self.fnmd=pygame.font.Font(None,19)
            self.fnlg=pygame.font.Font(None,22); self.fnxl=pygame.font.Font(None,32)
            self.fnttl=pygame.font.Font(None,62)

        self.sim=Simulation()
        self.cam=Camera()
        self.curtab=0; self.loading=False; self.setupdone=False
        self.showheatmap=False; self.showroads=True; self.showambcov=False
        self.autoplay=False; self.speedidx=1; self.lastautoms=0
        self.isomode=True   # 3D iso vs flat 2D
        self.nightmode=True # night vs day palette

        self.teamprevx=0.0; self.teamprevy=0.0; self.teamlerp=1.0
        self.teamtrail=[]
        self.ripples=[]; self.rescuepings=[]; self.sparkles=[]
        self.showcompletion=False; self.showstats=False; self.prevcivcnt=0
        self.routepulset=0.0; self.floodsteps=[]
        self.showshortcuts=False
        self.showpolice=True   # toggle officer markers on Crime tab
        self.resetpresstime=-999.0
        self.statcovpct=0.0
        self.totalfloods=0; self.totalreroutes=0
        # intro
        self.introDone=False; self.introStart=pygame.time.get_ticks()/1000.0
        # residential palette per-node (stable)
        self.respals={}
        # stars (fixed seed for reproducibility)
        random.seed(42)
        self.stars=[(random.randint(0,1280),random.randint(0,500)) for _ in range(40)]
        random.seed()

        self.lw=225; self.rw=265; self.topH=112; self.botH=142
        self.maparea=pygame.Rect(0,0,0,0)
        # 2D map params
        self.cellsize=0; self.offsetx=0; self.offsety=0

        self.btnsetup=self.btnauto=self.btnspeed=self.btnreset=pygame.Rect(0,0,0,0)
        self.btnnext=self.btnrunall=self.btnheatmap=self.btnroads=pygame.Rect(0,0,0,0)
        self.btnambcov=self.btnviewrep=self.btniso=self.btnday=pygame.Rect(0,0,0,0)
        self.btnfitview=self.btnstatsclose=self.btnstatsreset=pygame.Rect(0,0,0,0)
        self.tabrects=[]
        self.hovnode=None; self.hovedge=None
        self.mousex=0; self.mousey=0
        self.logscroll=0; self.pulse=0.0
        self.clock=pygame.time.Clock()
        self._hookflood()

    def _hookflood(self):
        def onblock(srcid,dstid):
            if not self.setupdone: return
            self.totalfloods+=1
            if self.sim.step not in self.floodsteps: self.floodsteps.append(self.sim.step)
            try:
                x1,y1=self._nc(srcid); x2,y2=self._nc(dstid)
                self.ripples.append(Ripple((x1+x2)//2,(y1+y2)//2))
            except: pass
        self.sim.graph.onblocked.append(onblock)

    def run(self):
        # vanilla game loop: poll input, maybe advance sim, draw frame
        while True:
            dt=min(self.clock.tick(60)/1000.0,0.05)
            self.pulse=(self.pulse+dt*2.8)%(2*math.pi)
            self.routepulset=(self.routepulset+dt/1.5)%1.0
            now=pygame.time.get_ticks()
            if self.autoplay and self.setupdone and not self.sim.finished and now-self.lastautoms>=SPEEDS[self.speedidx]:
                self.lastautoms=now; self._dostep()
            if self.teamlerp<1.0: self.teamlerp=min(1.0,self.teamlerp+dt*7.0)
            for r in self.ripples: r.update(dt)
            for p in self.rescuepings: p.update(dt)
            for s in self.sparkles: s.update(dt)
            self.ripples=[r for r in self.ripples if r.life>0]
            self.rescuepings=[p for p in self.rescuepings if p.life>0]
            self.sparkles=[s for s in self.sparkles if s.life>0]
            if self.setupdone:
                self.sim.expire_floods()
            if self.setupdone and self.sim.router:
                newcnt=len(self.sim.router.unvisited)
                if newcnt<self.prevcivcnt:
                    # a civilian was just rescued — find the one that left unvisited
                    # flash a ping at the team's current position
                    try:
                        if self.sim.teampos is not None:
                            rx,ry=self._nc(self.sim.teampos); self.rescuepings.append(RescuePing(rx,ry))
                    except: pass
                self.prevcivcnt=newcnt
            if self.setupdone and self.sim.finished and not self.showcompletion:
                self.showcompletion=True
                cx=self.maparea.x+self.maparea.width//2; cy=self.maparea.y+self.maparea.height//2
                for _ in range(80): self.sparkles.append(Sparkle(cx,cy))
            for event in pygame.event.get():
                if event.type==pygame.QUIT: pygame.quit(); sys.exit()
                if event.type==pygame.VIDEORESIZE:
                    self.W,self.H=event.w,event.h
                    self.screen=pygame.display.set_mode((self.W,self.H),pygame.RESIZABLE)
                self._handleinput(event)
            self._updatemapsizes()
            self._updatecaption()
            if not self.introDone: self._drawintro()
            else: self._draw()
            pygame.display.flip()

    def _handleinput(self,ev):
        if ev.type==pygame.MOUSEMOTION:
            self.mousex,self.mousey=ev.pos
            if self.cam.dragging:
                self.cam.ox+=ev.pos[0]-self.cam.lastmx
                self.cam.oy+=ev.pos[1]-self.cam.lastmy
                self.cam.lastmx,self.cam.lastmy=ev.pos
            self.hovnode=self._nodeunder(ev.pos)
            self.hovedge=self._edgeunder(ev.pos) if not self.isomode else None
        if ev.type==pygame.MOUSEBUTTONDOWN:
            if not self.introDone: self.introDone=True; return
            mx,my=ev.pos
            if ev.button==3 and self.isomode:  # right click drag
                self.cam.dragging=True; self.cam.lastmx,self.cam.lastmy=mx,my; return
            if ev.button==4 and self.isomode:  # scroll up = zoom in
                self.cam.scale=min(2.0,self.cam.scale*1.1)
            if ev.button==5 and self.isomode:  # scroll down = zoom out
                self.cam.scale=max(0.3,self.cam.scale/1.1)
            if self.showstats:
                if self.btnstatsclose.collidepoint(mx,my): self.showstats=False; return
                if self.btnstatsreset.collidepoint(mx,my): self._doreset(); return
                return  # eat all clicks while stats open
            if self.showcompletion and self.btnviewrep.collidepoint(mx,my):
                self.showcompletion=False; self.showstats=True; return
            if self.btnsetup.collidepoint(mx,my):
                if not self.setupdone and not self.loading: self._dosetup()
            elif self.btnnext.collidepoint(mx,my):
                if self.setupdone and not self.sim.finished and not self.autoplay: self._dostep()
            elif self.btnrunall.collidepoint(mx,my):
                if self.setupdone and not self.sim.finished:
                    self.autoplay=False; self.sim.runall(); self.logscroll=0
            elif self.btnauto.collidepoint(mx,my):
                if self.setupdone and not self.sim.finished:
                    self.autoplay=not self.autoplay; self.lastautoms=pygame.time.get_ticks()
            elif self.btnspeed.collidepoint(mx,my): self.speedidx=(self.speedidx+1)%len(SPEEDS)
            elif self.btnheatmap.collidepoint(mx,my): self.showheatmap=not self.showheatmap
            elif self.btnroads.collidepoint(mx,my): self.showroads=not self.showroads
            elif self.btnambcov.collidepoint(mx,my): self.showambcov=not self.showambcov
            elif self.btniso.collidepoint(mx,my): self.isomode=not self.isomode
            elif self.btnday.collidepoint(mx,my): self.nightmode=not self.nightmode
            elif self.btnreset.collidepoint(mx,my):
                now2=pygame.time.get_ticks()/1000.0
                if now2-self.resetpresstime<1.0: self._doreset()
                else: self.resetpresstime=now2
            elif self.btnfitview.collidepoint(mx,my) and self.setupdone and self.isomode:
                self.cam.fit(self.sim.graph.rows,self.sim.graph.cols,
                             self.maparea.width,self.maparea.height,self.maparea.x,self.maparea.y)
            for i,tr in enumerate(self.tabrects):
                if tr.collidepoint(mx,my): self.curtab=i
        if ev.type==pygame.MOUSEBUTTONUP:
            if ev.button==3: self.cam.dragging=False
        if ev.type==pygame.MOUSEWHEEL and self.isomode:
            self.cam.scale=max(0.3,min(2.0,self.cam.scale*(1.1 if ev.y>0 else 0.91)))
        if ev.type==pygame.KEYDOWN: self._key(ev.key)
        if ev.type==pygame.MOUSEWHEEL and not self.isomode:
            self.logscroll=max(0,self.logscroll-ev.y*2)

    def _key(self,key):
        if not self.introDone: self.introDone=True; return
        if key==pygame.K_SPACE:
            if self.setupdone and not self.sim.finished and not self.autoplay: self._dostep()
        elif key==pygame.K_a:
            if self.setupdone and not self.sim.finished:
                self.autoplay=not self.autoplay; self.lastautoms=pygame.time.get_ticks()
        elif key==pygame.K_s: self.speedidx=(self.speedidx+1)%len(SPEEDS)
        elif key==pygame.K_r:
            now2=pygame.time.get_ticks()/1000.0
            if now2-self.resetpresstime<1.0: self._doreset()
            else: self.resetpresstime=now2
        elif key==pygame.K_h: self.showheatmap=not self.showheatmap
        elif key==pygame.K_c: self.showambcov=not self.showambcov
        elif key in (pygame.K_F1,pygame.K_SLASH): self.showshortcuts=not self.showshortcuts
        elif pygame.K_1<=key<=pygame.K_5: self.curtab=key-pygame.K_1
        elif key==pygame.K_f: 
            if self.setupdone and self.isomode:
                self.cam.fit(self.sim.graph.rows,self.sim.graph.cols,
                             self.maparea.width,self.maparea.height,self.maparea.x,self.maparea.y)
        elif key==pygame.K_TAB: self.isomode=not self.isomode
        elif key==pygame.K_n: self.nightmode=not self.nightmode

    def _doreset(self):
        self.autoplay=False; self.ripples=[]; self.rescuepings=[]; self.sparkles=[]
        self.showcompletion=False; self.showstats=False; self.floodsteps=[]; self.totalfloods=0; self.totalreroutes=0
        self.sim=Simulation(); self._hookflood()
        self.setupdone=False; self.loading=False; self.showheatmap=False; self.showambcov=False
        self.logscroll=0; self.teamlerp=1.0; self.teamtrail=[]; self.prevcivcnt=0
        self.resetpresstime=-999.0; self.respals={}; self.showpolice=True

    def _dosetup(self):
        self.loading=True
        def worker():
            self.sim.setup()
            if self.sim.teampos is not None:
                cx,cy=self._nc(self.sim.teampos)
                self.teamprevx=float(cx); self.teamprevy=float(cy)
                self.teamtrail=[(int(cx),int(cy))]*4
            self.prevcivcnt=len(self.sim.civilians)
            # assign stable palette to residential nodes
            for n in self.sim.graph.allnodes():
                if n.kind==residential and n.nodeid not in self.respals:
                    self.respals[n.nodeid]=random.choice(RESPAL)
            self.statcovpct=0.0; self._updatestatus()
            if self.isomode:
                self.cam.fit(self.sim.graph.rows,self.sim.graph.cols,
                             self.maparea.width,self.maparea.height,self.maparea.x,self.maparea.y)
            self.setupdone=True; self.loading=False
        threading.Thread(target=worker,daemon=True).start()

    def _dostep(self):
        if not self.setupdone or self.sim.finished: return
        prevpos=self.sim.teampos; self.sim.nextstep(); newpos=self.sim.teampos
        self.totalreroutes=self.sim.reroutecount
        self.logscroll=0
        if newpos!=prevpos and prevpos is not None and newpos is not None:
            px,py=self._nc(prevpos)
            self.teamprevx=float(px); self.teamprevy=float(py)
            self.teamtrail.append((int(px),int(py)))
            if len(self.teamtrail)>4: self.teamtrail.pop(0)
            self.teamlerp=0.0
        self._updatestatus()

    def _updatestatus(self):
        if not self.setupdone: return
        nodes=list(self.sim.graph.allnodes())
        total=len(nodes); cov=sum(1 for n in nodes if n.ambcov)
        self.statcovpct=cov/total if total>0 else 0.0

    def _updatemapsizes(self):
        self.maparea=pygame.Rect(self.lw,self.topH,self.W-self.lw-self.rw,self.H-self.topH-self.botH)
        if not self.setupdone: return
        if not self.isomode:
            g=self.sim.graph
            cw=self.maparea.width//g.cols; ch=self.maparea.height//g.rows
            self.cellsize=max(14,min(cw,ch))
            tw=self.cellsize*g.cols; th=self.cellsize*g.rows
            self.offsetx=self.maparea.x+(self.maparea.width-tw)//2
            self.offsety=self.maparea.y+(self.maparea.height-th)//2

    def _nc(self,nodeid):
        """screen center of a node — works in both iso and flat mode"""
        n=self.sim.graph.nodes[nodeid]
        if self.isomode:
            sx,sy=self.cam.g2s(n.row,n.col,0)
            return sx,sy+int(self.cam.ISO_H)
        return self.offsetx+n.col*self.cellsize+self.cellsize//2, self.offsety+n.row*self.cellsize+self.cellsize//2

    def _nodeunder(self,pos):
        if not self.setupdone: return None
        mx,my=pos
        if self.isomode:
            best=None; bestscore=20
            for n in self.sim.graph.allnodes():
                sx,sy=self.cam.g2s(n.row,n.col,0)
                hh=int(self.cam.ISO_H); hw=int(self.cam.ISO_W*0.5)
                cx=sx; cy=sy+hh
                dx=abs(mx-cx); dy=abs(my-cy)
                score=dx/hw+dy/hh
                if score<1.0 and score<bestscore: bestscore=score; best=n
            return best
        for n in self.sim.graph.allnodes():
            x=self.offsetx+n.col*self.cellsize; y=self.offsety+n.row*self.cellsize
            if x<=mx<=x+self.cellsize and y<=my<=y+self.cellsize: return n
        return None

    def _edgeunder(self,pos):
        if not self.setupdone or self.isomode: return None
        mx,my=pos
        for key,e in self.sim.graph.edgemap.items():
            if not e.built: continue
            x1,y1=self._nc(e.src.nodeid); x2,y2=self._nc(e.dst.nodeid)
            dx,dy=x2-x1,y2-y1; l2=dx*dx+dy*dy
            if l2==0: continue
            t=max(0.0,min(1.0,((mx-x1)*dx+(my-y1)*dy)/l2))
            px=x1+t*dx; py=y1+t*dy
            if math.sqrt((mx-px)**2+(my-py)**2)<8: return e
        return None

    def _teampos_lerped(self):
        if self.sim.teampos is None: return 0,0
        tx,ty=self._nc(self.sim.teampos)
        t=self._ease(self.teamlerp)
        return int(self.teamprevx+(tx-self.teamprevx)*t),int(self.teamprevy+(ty-self.teamprevy)*t)

    @staticmethod
    def _ease(t): return t*t*(3-2*t)

    def _updatecaption(self):
        if self.setupdone:
            rem=len(self.sim.router.unvisited) if self.sim.router else 0
            af=len(self.sim.active_floods)
            pygame.display.set_caption(
                f"CityMind | Step {self.sim.step}/{self.sim.maxsteps} "
                f"| {rem} civilian{'s' if rem!=1 else ''} remaining "
                f"| {af} flooded road{'s' if af!=1 else ''} (timed) "
                f"| {self.totalfloods} flood event{'s' if self.totalfloods!=1 else ''}")
        else:
            pygame.display.set_caption("CityMind | Urban Intelligence System")

    def _bgcol(self): return daybg if not self.nightmode else bg
    def _panelcol(self): return daypanel if not self.nightmode else panelbg
    def _bld3d(self,kind):
        src=bldDay if not self.nightmode else bld3d
        return src.get(kind,bld3d[empty])

    # ── cinematic intro ──────────────────────────────────────────────
    def _drawintro(self):
        t=pygame.time.get_ticks()/1000.0-self.introStart
        self.screen.fill(bg)
        cx=self.W//2; cy=self.H//2
        if t<1.3:
            nch=int((t/1.3)*8)
            s=self.fnttl.render("CityMind"[:nch],True,acc)
            self.screen.blit(s,(cx-s.get_width()//2,cy-55))
            if int(t*3)%2==0:
                cur=self.fnttl.render("_",True,acc2)
                self.screen.blit(cur,(cx-s.get_width()//2+s.get_width(),cy-55))
        elif t<2.2:
            s=self.fnttl.render("CityMind",True,acc)
            self.screen.blit(s,(cx-s.get_width()//2,cy-55))
            alpha=int(255*min(1.0,(t-1.3)/0.7))
            for i,(line,font,col) in enumerate([
                ("Urban Intelligence System",self.fnxl,acc2),
                ("AI Semester Project  |  5 Algorithms. One City.",self.fnsm,dim)]):
                r=font.render(line,True,col); surf=pygame.Surface(r.get_size(),pygame.SRCALPHA)
                surf.blit(r,(0,0)); surf.set_alpha(alpha)
                self.screen.blit(surf,(cx-r.get_width()//2,cy+12+i*32))
        elif t<3.0:
            s=self.fnttl.render("CityMind",True,acc)
            sub=self.fnxl.render("Urban Intelligence System",True,acc2)
            self.screen.blit(s,(cx-s.get_width()//2,cy-55))
            self.screen.blit(sub,(cx-sub.get_width()//2,cy+12))
            ph=self.fnsm.render("Press any key or click to skip",True,dim)
            self.screen.blit(ph,(cx-ph.get_width()//2,cy+100))
        else:
            self.introDone=True

    # ── master draw ──────────────────────────────────────────────────
    def _draw(self):
        self.screen.fill(self._bgcol())
        if self.nightmode:
            for sx,sy in self.stars:
                pygame.draw.circle(self.screen,(255,255,255),(sx%self.W,sy%self.H),1)
        self._panelbgs()
        self._drawtopbar()
        self._drawleftpanel()
        self._drawrightpanel()
        self._drawbottombar()
        self._drawmap()
        self._drawcompletionoverlay()
        self._drawshortcuts()
        self._drawtopglow()
        self._drawhover()
        self._drawstatsoverlay()

    def _panelbgs(self):
        pc=self._panelcol()
        for r in [pygame.Rect(0,self.topH,self.lw,self.H-self.topH),
                  pygame.Rect(self.W-self.rw,self.topH,self.rw,self.H-self.topH),
                  pygame.Rect(0,self.H-self.botH,self.W,self.botH)]:
            pygame.draw.rect(self.screen,pc,r)
            if self.nightmode:
                d=pygame.Surface(r.size,pygame.SRCALPHA)
                for xi in range(0,r.width+r.height,8):
                    pygame.draw.line(d,(255,255,255,10),(xi,0),(xi-r.height,r.height),1)
                self.screen.blit(d,r.topleft)
        pygame.draw.line(self.screen,pbdr,(self.lw,self.topH),(self.lw,self.H),2)
        pygame.draw.line(self.screen,pbdr,(self.W-self.rw,self.topH),(self.W-self.rw,self.H),2)
        pygame.draw.line(self.screen,pbdr,(0,self.H-self.botH),(self.W,self.H-self.botH),2)

    def _drawtopglow(self):
        if not self.nightmode: return
        ph=(math.sin(self.pulse*0.5)+1)/2
        r=int(acc[0]+(acc2[0]-acc[0])*ph); g=int(acc[1]+(acc2[1]-acc[1])*ph); b=int(acc[2]+(acc2[2]-acc[2])*ph)
        surf=pygame.Surface((self.W,3),pygame.SRCALPHA)
        for xi in range(self.W):
            a=100+int(70*math.sin(xi/self.W*math.pi))
            pygame.draw.line(surf,(r,g,b,a),(xi,0),(xi,2))
        self.screen.blit(surf,(0,0))

    # ── top bar ──────────────────────────────────────────────────────
    def _drawtopbar(self):
        pygame.draw.rect(self.screen,self._panelcol(),(0,0,self.W,self.topH))
        pygame.draw.line(self.screen,pbdr,(0,self.topH),(self.W,self.topH),2)
        self.screen.blit(self.fnxl.render("CityMind",True,acc),(16,8))
        self.screen.blit(self.fnsm.render("Urban Intelligence System  |  AI Semester Project",True,dim),(18,42))
        if self.loading: badge,bcol="* INITIALIZING...",warn
        elif not self.setupdone: badge,bcol="* READY",dim
        elif self.sim.finished: badge,bcol="[DONE]",good
        elif self.autoplay: badge,bcol=f"[AUTO] [{SPDLBLS[self.speedidx]}]",acc2
        else: badge,bcol=f"* STEP {self.sim.step}/{self.sim.maxsteps}",acc
        bt=self.fnlg.render(badge,True,bcol); self.screen.blit(bt,(self.W-bt.get_width()-14,10))
        tw2,th2=100,30; tx0,ty0=16,70; self.tabrects=[]
        for i,name in enumerate(TABS):
            r=pygame.Rect(tx0+i*(tw2+5),ty0,tw2,th2); self.tabrects.append(r)
            active=(i==self.curtab)
            pygame.draw.rect(self.screen,acc if active else (22,30,55),r,border_radius=6)
            if active: pygame.draw.rect(self.screen,acc,r,2,border_radius=6)
            ts=self.fnmd.render(name,True,txt if active else dim)
            self.screen.blit(ts,(r.x+(tw2-ts.get_width())//2,r.y+(th2-ts.get_height())//2))
        ox=tx0+len(TABS)*(tw2+5)+12
        for label,state,attr,hicol in [
            ("Roads",self.showroads,"btnroads",roadcol),
            ("Amb.Cov",self.showambcov,"btnambcov",ambcol),
            ("Heatmap",self.showheatmap,"btnheatmap",(170,75,215))]:
            r=pygame.Rect(ox,ty0,86,th2); setattr(self,attr,r)
            c1=tuple(max(0,x//3) for x in hicol) if not state else tuple(min(255,x//2) for x in hicol)
            pygame.draw.rect(self.screen,c1,r,border_radius=6)
            pygame.draw.rect(self.screen,hicol if state else pbdr,r,2,border_radius=6)
            lt=self.fnsm.render(("[OK] " if state else "")+label,True,txt)
            self.screen.blit(lt,(r.x+(86-lt.get_width())//2,r.y+(th2-lt.get_height())//2)); ox+=90
        # 3D/2D toggle
        self.btniso=pygame.Rect(ox,ty0,76,th2)
        pygame.draw.rect(self.screen,(15,45,80) if self.isomode else (22,30,55),self.btniso,border_radius=6)
        pygame.draw.rect(self.screen,acc if self.isomode else pbdr,self.btniso,2,border_radius=6)
        it=self.fnsm.render("3D ISO [Tab]" if not self.isomode else "2D [Tab]",True,txt)
        self.screen.blit(it,(self.btniso.x+(76-it.get_width())//2,self.btniso.y+(th2-it.get_height())//2)); ox+=80
        # night/day toggle
        self.btnday=pygame.Rect(ox,ty0,76,th2)
        pygame.draw.rect(self.screen,(30,25,60) if self.nightmode else (200,175,80),self.btnday,border_radius=6)
        pygame.draw.rect(self.screen,acc if self.nightmode else warn,self.btnday,2,border_radius=6)
        dt2=self.fnsm.render("* Night [N]" if self.nightmode else "* Day [N]",True,txt)
        self.screen.blit(dt2,(self.btnday.x+(76-dt2.get_width())//2,self.btnday.y+(th2-dt2.get_height())//2))

    # ── left panel ───────────────────────────────────────────────────
    def _drawleftpanel(self):
        mx2,my2=pygame.mouse.get_pos(); x0=8; y=self.topH+10
        self.screen.blit(self.fnlg.render("LEGEND",True,txt),(x0,y)); y+=24
        for kind,col in nodecols.items():
            if kind==empty: continue
            # mini iso cube icon
            pts=[(x0+14,y+4),(x0+20,y+8),(x0+14,y+12),(x0+8,y+8)]
            pygame.draw.polygon(self.screen,col,pts)
            pygame.draw.polygon(self.screen,tuple(max(0,c-50) for c in col),[(x0+8,y+8),(x0+14,y+12),(x0+14,y+16),(x0+8,y+12)])
            pygame.draw.polygon(self.screen,tuple(min(255,c+30) for c in col),[(x0+14,y+12),(x0+20,y+8),(x0+20,y+12),(x0+14,y+16)])
            ls=self.fnsm.render(kind,True,txt)
            pygame.draw.rect(self.screen,(18,25,50),(x0+24,y-1,ls.get_width()+8,16),border_radius=6)
            self.screen.blit(ls,(x0+28,y)); y+=20
        y+=4; pygame.draw.line(self.screen,pbdr,(x0,y),(self.lw-10,y),1); y+=8
        pygame.draw.line(self.screen,roadcol,(x0,y+7),(x0+18,y+7),3)
        self.screen.blit(self.fnsm.render("MST Road",True,dim),(x0+22,y)); y+=17
        pygame.draw.circle(self.screen,ambcol,(x0+8,y+7),6)
        self.screen.blit(self.fnsm.render("Ambulance",True,dim),(x0+20,y)); y+=17
        pygame.draw.circle(self.screen,teamcol,(x0+8,y+7),7)
        self.screen.blit(self.fnsm.render("Medical Team",True,dim),(x0+20,y)); y+=17
        pygame.draw.circle(self.screen,civcol,(x0+8,y+7),5)
        self.screen.blit(self.fnsm.render("Civilian",True,dim),(x0+20,y)); y+=20
        pygame.draw.line(self.screen,(255,80,180),(x0,y+7),(x0+18,y+7),2)
        self.screen.blit(self.fnsm.render("Primary Path (Roads Tab)",True,dim),(x0+22,y)); y+=17
        pygame.draw.line(self.screen,(80,255,120),(x0,y+7),(x0+18,y+7),2)
        self.screen.blit(self.fnsm.render("Redundant Path (Roads Tab)",True,dim),(x0+22,y)); y+=20
        # police badge legend entry
        for lvl,bc in [("High",(220,40,40)),("Med",(210,130,25)),("Low",(30,110,220))]:
            pygame.draw.polygon(self.screen,bc,[(x0+8,y+2),(x0+14,y+2),(x0+14,y+9),(x0+8,y+9),(x0+11,y+13)])
            self.screen.blit(self.fnsm.render(f"Police ({lvl} risk)",True,dim),(x0+18,y)); y+=15
        pygame.draw.line(self.screen,pbdr,(x0,y),(self.lw-10,y),1); y+=8
        self.screen.blit(self.fnlg.render("SYSTEM STATUS",True,txt),(x0,y)); y+=22
        if self.setupdone:
            nodes=list(self.sim.graph.allnodes()); blk=sum(1 for n in nodes if n.blocked)
            sts=[("GRAPH INTEGRITY",blk==0,"Clear" if blk==0 else f"{blk} blocked"),
                 ("AMB COVERAGE",self.statcovpct>0.8,f"{self.statcovpct*100:.0f}%"),
                 ("ROUTER",(self.sim.router and not self.sim.router.done) or self.sim.finished,"Active")]
            for label,ok,sub in sts:
                pygame.draw.circle(self.screen,good if ok else warn,(x0+6,y+7),5)
                self.screen.blit(self.fnsm.render(label,True,txt),(x0+15,y))
                self.screen.blit(self.fnsm.render(sub,True,dim),(x0+15,y+13)); y+=28
        else:
            for lb in ["GRAPH INTEGRITY","AMB COVERAGE","ROUTER"]:
                pygame.draw.circle(self.screen,dim,(x0+6,y+7),5)
                self.screen.blit(self.fnsm.render(lb,True,dim),(x0+15,y)); y+=22
        y+=4; pygame.draw.line(self.screen,pbdr,(x0,y),(self.lw-10,y),1); y+=8
        bw=self.lw-18; bh=34
        def btn(rect,c1,c2,label):
            hov=rect.collidepoint(mx2,my2)
            pygame.draw.rect(self.screen,c1,rect,border_radius=7)
            bc=tuple(min(255,c+55) for c in c2) if hov else c2
            pygame.draw.rect(self.screen,bc,rect,2,border_radius=7)
            if hov:
                g2=pygame.Surface((rect.width,rect.height),pygame.SRCALPHA)
                pygame.draw.rect(g2,(*bc,20),(0,0,rect.width,rect.height),border_radius=7)
                self.screen.blit(g2,rect.topleft)
            lt=self.fnmd.render(label,True,txt)
            self.screen.blit(lt,(rect.x+(rect.width-lt.get_width())//2,rect.y+(rect.height-lt.get_height())//2))
        if self.loading: c1b,c2b,lb=(45,45,15),warn,"Initializing..."
        elif self.setupdone: c1b,c2b,lb=(15,50,25),good,"System Ready [OK]"
        else: c1b,c2b,lb=(18,50,125),acc,"Initialize System"
        self.btnsetup=pygame.Rect(x0,y,bw,bh); btn(self.btnsetup,c1b,c2b,lb); y+=bh+7
        self.btnauto=pygame.Rect(x0,y,bw,bh)
        btn(self.btnauto,(15,70,60) if self.autoplay else (20,28,50),
            acc2 if self.autoplay else pbdr,"Stop Auto-Play [A]" if self.autoplay else "> Auto-Play [A]"); y+=bh+6
        self.btnspeed=pygame.Rect(x0,y,bw,bh)
        btn(self.btnspeed,(18,24,44),pbdr,f"Speed: {SPDLBLS[self.speedidx]} [S]"); y+=bh+7
        now2=pygame.time.get_ticks()/1000.0; pend=(now2-self.resetpresstime)<1.0
        self.btnreset=pygame.Rect(x0,y,bw,bh)
        btn(self.btnreset,(100,25,25) if pend else (70,18,18),(255,120,120) if pend else bad,
            "Press R again!" if pend else "Reset [R]")

    # ── right panel ──────────────────────────────────────────────────
    def _drawrightpanel(self):
        rx=self.W-self.rw; x0=rx+8; y=self.topH+10
        self.screen.blit(self.fnlg.render("LIVE STATS",True,txt),(x0,y)); y+=24
        if self.setupdone:
            st=self.sim.statusdict(); rem=st["remaining"]
            cards=[("TEAM",str(st["teampos"]),teamcol),("CIVILIANS",f"{rem} left",civcol),
                   ("FLOODS",f"{len(self.sim.active_floods)} active / {self.totalfloods} ev",
                    bad if len(self.sim.active_floods)>0 else dim),
                   ("COVERAGE",f"{self.statcovpct*100:.0f}%",good if self.statcovpct>0.8 else warn),
                   ("ROAD COST",str(st["roadcost"]),acc),("REROUTES",str(self.totalreroutes),warn if self.totalreroutes>0 else dim)]
            cw3=(self.rw-22)//2; ch3=34
            for i,(lb,val,col) in enumerate(cards):
                cx3=x0+(i%2)*(cw3+4); cy3=y+(i//2)*(ch3+4)
                pygame.draw.rect(self.screen,(16,22,44),(cx3,cy3,cw3,ch3),border_radius=5)
                pygame.draw.rect(self.screen,pbdr,(cx3,cy3,cw3,ch3),1,border_radius=5)
                self.screen.blit(self.fnsm.render(lb,True,dim),(cx3+5,cy3+3))
                self.screen.blit(self.fnmd.render(str(val)[:10],True,col),(cx3+5,cy3+17))
            y+=3*(ch3+4)+10
            self.screen.blit(self.fnsm.render("RISK DISTRIBUTION",True,dim),(x0,y)); y+=16
            nodes=list(self.sim.graph.allnodes()); total=max(1,len(nodes))
            rcnts={"High":0,"Medium":0,"Low":0}
            for n in nodes: rcnts[n.risklvl]=rcnts.get(n.risklvl,0)+1
            bw3=(self.rw-26)//3
            for i,(lvl,col) in enumerate(riskcols.items()):
                bx3=x0+i*(bw3+3); pct=rcnts[lvl]/total
                pygame.draw.rect(self.screen,(20,27,50),(bx3,y,bw3,40),border_radius=3)
                bh3=max(2,int(pct*38))
                pygame.draw.rect(self.screen,col,(bx3,y+40-bh3,bw3,bh3),border_radius=3)
                ct=self.fnsm.render(str(rcnts[lvl]),True,col)
                self.screen.blit(ct,(bx3+(bw3-ct.get_width())//2,y+42))
            y+=60

            # ── CSP violation summary (Layout tab) ──────────────────
            st2=self.sim.statusdict()
            viol=st2.get("violations",0)
            rule=st2.get("conflictrule","")
            pygame.draw.line(self.screen,pbdr,(x0,y),(self.W-8,y),1); y+=6
            self.screen.blit(self.fnsm.render("CSP LAYOUT RESULT",True,dim),(x0,y)); y+=14
            if viol==0:
                self.screen.blit(self.fnsm.render("[OK] All constraints satisfied",True,good),(x0,y)); y+=14
            else:
                self.screen.blit(self.fnsm.render(f"[!] {viol} violation(s)",True,warn),(x0,y)); y+=14
                if rule and rule!="none":
                    # wrap long rule text
                    short=rule[:32]+"..." if len(rule)>32 else rule
                    self.screen.blit(self.fnsm.render(f"Rule: {short}",True,bad),(x0,y)); y+=14

            # ── Police allocation summary (Crime tab) ───────────────
            pygame.draw.line(self.screen,pbdr,(x0,y),(self.W-8,y),1); y+=6
            self.screen.blit(self.fnsm.render("POLICE DEPLOYMENT",True,dim),(x0,y)); y+=14
            omap=st2.get("officermap",{})
            if omap:
                total_off=sum(omap.values())
                high_zones=sum(1 for nid in omap if self.sim.graph.nodes[nid].risklvl=="High")
                self.screen.blit(self.fnsm.render(f"10 officers / {len(omap)} zones",True,(100,200,255)),(x0,y)); y+=13
                self.screen.blit(self.fnsm.render(f"{high_zones} High-risk zones covered",True,bad),(x0,y)); y+=13
            else:
                self.screen.blit(self.fnsm.render("Run setup to allocate",True,dim),(x0,y)); y+=13

            # ── ML pipeline label ───────────────────────────────────
            pygame.draw.line(self.screen,pbdr,(x0,y),(self.W-8,y),1); y+=6
            self.screen.blit(self.fnsm.render("ML PIPELINE",True,dim),(x0,y)); y+=14
            self.screen.blit(self.fnsm.render("Step1: K-Means (Unsupervised)",True,acc2),(x0,y)); y+=13
            self.screen.blit(self.fnsm.render("Step3: Decision Tree (Supervised)",True,acc),(x0,y)); y+=13

        else:
            self.screen.blit(self.fnsm.render("Waiting for setup",True,dim),(x0,y)); y+=40
        pygame.draw.line(self.screen,pbdr,(x0,y),(self.W-8,y),1); y+=6
        self.screen.blit(self.fnlg.render("EVENT LOG",True,txt),(x0,y)); y+=22
        lh=15; avail=self.H-self.botH-y-6; maxln=avail//lh
        log=self.sim.eventlog or []; start=max(0,len(log)-maxln-self.logscroll)
        for msg in log[start:start+maxln]:
            ml=msg.lower()
            body=msg[msg.find(":")+1:].strip() if ":" in msg else msg
            if "[flood]" in ml: bdg,bc="FLOOD",bad
            elif "[replan]" in ml: bdg,bc="REPLAN",warn
            elif "[defer]" in ml: bdg,bc="DEFER",warn
            elif "[nearest]" in ml: bdg,bc="NEAR",acc2
            elif "[route]" in ml: bdg,bc="ROUTE",acc2
            elif "[rescue]" in ml or "[outcome]" in ml: bdg,bc="RESCUE",good
            elif "[move]" in ml: bdg,bc="MOVE",dim
            elif "[integrate]" in ml: bdg,bc="LINK",acc
            elif "[routing]" in ml: bdg,bc="ROUTE",acc2
            elif "flood" in ml: bdg,bc="FLOOD",bad
            elif "replan" in ml: bdg,bc="REPLAN",warn
            elif "[route]" in ml or "route" in ml and "next civilian" in ml: bdg,bc="ROUTE",acc2
            elif "rescue" in ml or "reached" in ml or "mission" in ml: bdg,bc="RESCUE",good
            elif "police" in ml or "officer" in ml: bdg,bc="POLICE",(100,200,255)
            elif "mst" in ml or "built" in ml or "step 0" in ml: bdg,bc="SETUP",acc
            elif "unsupervised" in ml or "supervised" in ml: bdg,bc="ML",acc2
            else: bdg,bc="INFO",dim
            bs=self.fnsm.render(f"[{bdg}]",True,bc)
            self.screen.blit(bs,(x0,y))
            mt=self.fnsm.render(body[:52],True,bc)
            if y+lh<self.H-self.botH-4: self.screen.blit(mt,(x0+bs.get_width()+6,y))
            y+=lh

    # ── bottom bar ───────────────────────────────────────────────────
    def _drawbottombar(self):
        barby=self.H-self.botH; x0=8
        mmx=x0; mmy=barby+12; mmw=110; mmh=110
        pygame.draw.rect(self.screen,(14,18,36),(mmx,mmy,mmw,mmh),border_radius=5)
        pygame.draw.rect(self.screen,pbdr,(mmx,mmy,mmw,mmh),1,border_radius=5)
        mt=self.fnsm.render("MINI-MAP",True,dim)
        self.screen.blit(mt,(mmx+mmw//2-mt.get_width()//2,mmy+1))
        if self.setupdone:
            g=self.sim.graph; dw=mmw/g.cols; dh=(mmh-14)/g.rows
            for n in g.allnodes():
                nx2=int(mmx+n.col*dw); ny2=int(mmy+14+n.row*dh)
                pygame.draw.rect(self.screen,nodecols.get(n.kind,(22,28,46)),(nx2,ny2,max(2,int(dw)-1),max(2,int(dh)-1)))
            for pid in self.sim.ambplaces:
                an=g.nodes[pid]; ax=int(mmx+an.col*dw+dw//2); ay=int(mmy+14+an.row*dh+dh//2)
                pygame.draw.circle(self.screen,ambcol,(ax,ay),3)
            if self.sim.teampos is not None:
                tn=g.nodes[self.sim.teampos]
                pygame.draw.circle(self.screen,teamcol,(int(mmx+tn.col*dw+dw//2),int(mmy+14+tn.row*dh+dh//2)),3)
        self.btnnext=pygame.Rect(mmx+mmw+10,barby+52,118,34)
        self.btnrunall=pygame.Rect(mmx+mmw+133,barby+52,118,34)
        act4=self.setupdone and not self.sim.finished and not self.autoplay
        nc2=(22,60,120) if act4 else (18,22,40); bc2=acc if act4 else pbdr
        for btn2,label in [(self.btnnext,"> Next [Space]"),(self.btnrunall,">> Run All")]:
            pygame.draw.rect(self.screen,nc2,btn2,border_radius=7)
            pygame.draw.rect(self.screen,bc2,btn2,2,border_radius=7)
            lt=self.fnmd.render(label,True,txt if act4 else dim)
            self.screen.blit(lt,(btn2.x+(btn2.width-lt.get_width())//2,btn2.y+(btn2.height-lt.get_height())//2))
        # timeline
        tlx=self.lw+20; tly=barby+18; tsz=18; tgap=4
        if self.setupdone:
            self.screen.blit(self.fnsm.render("SIMULATION TIMELINE",True,dim),(tlx,tly-14))
            for s in range(self.sim.maxsteps):
                cx3=tlx+s*(tsz+tgap); cy3=tly+tsz//2
                if s<self.sim.step: pygame.draw.circle(self.screen,acc,(cx3+tsz//2,cy3),tsz//2-1)
                elif s==self.sim.step:
                    pr=tsz//2-1+int(3*abs(math.sin(self.pulse)))
                    gs=pygame.Surface((pr*2+4,pr*2+4),pygame.SRCALPHA)
                    pygame.draw.circle(gs,(*acc,80),(pr+2,pr+2),pr)
                    self.screen.blit(gs,(cx3+tsz//2-pr-2,cy3-pr-2))
                    pygame.draw.circle(self.screen,acc2,(cx3+tsz//2,cy3),tsz//2-1,2)
                else: pygame.draw.circle(self.screen,pbdr,(cx3+tsz//2,cy3),tsz//2-1,1)
                if s in self.floodsteps or s+1 in self.floodsteps:
                    fw=self.fnsm.render("[!]",True,bad)
                    self.screen.blit(fw,(cx3+tsz//2-fw.get_width()//2,tly-12))
        # stat cards + buildings count
        if self.setupdone:
            st=self.sim.statusdict()
            nblds=sum(1 for n in self.sim.graph.allnodes() if n.kind!=empty)
            cards=[(f"BLDGS: {nblds}",str(nblds),acc),("Road Cost",str(st["roadcost"]),acc),("Max Dist",str(st["maxdist"]),warn)]
            cx0=self.lw+20; cw4=(self.W-self.rw-cx0-200)//3; cy4=barby+52; ch4=72
            for i,(lb,val,col) in enumerate(cards):
                cx4=cx0+i*(cw4+6)
                pygame.draw.rect(self.screen,(18,24,45),(cx4,cy4,cw4,ch4),border_radius=6)
                pygame.draw.rect(self.screen,pbdr,(cx4,cy4,cw4,ch4),1,border_radius=6)
                self.screen.blit(self.fnsm.render(lb,True,dim),(cx4+6,cy4+8))
                self.screen.blit(self.fnmd.render(str(val)[:14],True,col),(cx4+6,cy4+26))
        # fit view button
        if self.isomode:
            self.btnfitview=pygame.Rect(self.W-self.rw-120,barby+12,114,26)
            pygame.draw.rect(self.screen,(18,24,44),self.btnfitview,border_radius=6)
            pygame.draw.rect(self.screen,pbdr,self.btnfitview,1,border_radius=6)
            ft=self.fnsm.render("+ Reset View [F]",True,dim)
            self.screen.blit(ft,(self.btnfitview.x+(114-ft.get_width())//2,self.btnfitview.y+6))

    # ── map dispatcher ───────────────────────────────────────────────
    def _drawmap(self):
        pygame.draw.rect(self.screen,(9,12,24) if self.nightmode else (120,170,220),self.maparea)
        if not self.setupdone:
            cx=self.maparea.x+self.maparea.width//2; cy=self.maparea.y+self.maparea.height//2
            if self.loading:
                t2=pygame.time.get_ticks()/1000.0
                ms=self.fnlg.render("Building city...",True,acc)
                self.screen.blit(ms,(cx-ms.get_width()//2,cy-30))
                for i in range(8):
                    ang=math.pi*2*i/8+t2*3
                    pygame.draw.circle(self.screen,acc,(cx+int(math.cos(ang)*24),cy+12+int(math.sin(ang)*24)),4)
            else:
                ms=self.fnlg.render("Click 'Initialize System' to begin",True,dim)
                self.screen.blit(ms,(cx-ms.get_width()//2,cy-8))
            return
        if self.isomode: self._drawmapiso()
        else: self._drawmapflat()

    # ── ISOMETRIC 3D MAP ─────────────────────────────────────────────
    def _drawmapiso(self):
        g=self.sim.graph; cam=self.cam
        # sorted tiles back to front by row+col
        tiles=sorted(g.allnodes(),key=lambda n:n.row+n.col)
        # draw tiles (buildings) first
        for n in tiles:
            self._drawbldiso(n)
            # route highlight overlay
            if self.curtab==3 and self.sim.router and not self.sim.router.done:
                path=self.sim.router.getfullpath()
                if n.nodeid in path:
                    pts=cam.tile_diamond(n.row,n.col)
                    s=pygame.Surface((self.W,self.H),pygame.SRCALPHA)
                    pygame.draw.polygon(s,(*rtcol,40),pts)
                    self.screen.blit(s,(0,0))
            # ambulance coverage
            if (self.showambcov or self.curtab==2) and n.ambcov:
                pts=cam.tile_diamond(n.row,n.col)
                s=pygame.Surface((self.W,self.H),pygame.SRCALPHA)
                pygame.draw.polygon(s,(0,200,100,28),pts); self.screen.blit(s,(0,0))
        # draw roads ON TOP of ground tiles so they are always visible
        if self.showroads: self._drawroadsiso(tiles)
        # heatmap glows drawn AFTER buildings so they spread visibly between tiles
        if self.showheatmap or self.curtab==4:
            self._drawheatmap_glows_iso(tiles)
        # vehicles and entities
        for n in tiles:
            if self.curtab in (0,3) and self.sim.router:
                if n in self.sim.civilians:
                    idx=self.sim.civilians.index(n)
                    if n.nodeid in self.sim.router.unvisited: self._drawciviso(n)
            if self.curtab in (0,2) and n.nodeid in self.sim.ambplaces:
                self._drawambiso(n.nodeid)
            # police officer markers on Crime tab
            if self.curtab==4 and self.showpolice:
                omap=self.sim.officermap
                if n.nodeid in omap:
                    self._drawpoliceiso(n, omap[n.nodeid])
        if self.curtab in (0,3) and self.sim.teampos is not None:
            self._drawteamiso()
        if self.curtab==3 and self.sim.router and not self.sim.router.done:
            self._drawrouteiso()
        for rp in self.ripples: rp.draw(self.screen)
        for pp in self.rescuepings: pp.draw(self.screen)
        for sp in self.sparkles: sp.draw(self.screen)

    def _drawheatmap_glows_flat(self, g, cs):
        """Full-tile solid colour fill — perfectly aligned with the grid, clearly visible."""
        heat = pygame.Surface(self.maparea.size, pygame.SRCALPHA)
        ox   = self.offsetx - self.maparea.x
        oy   = self.offsety - self.maparea.y
        for n in g.allnodes():
            col = riskcols.get(n.risklvl, (80, 80, 80))
            pygame.draw.rect(heat, (*col, 210),
                             (ox + n.col*cs, oy + n.row*cs, cs, cs))
        self.screen.blit(heat, self.maparea.topleft)

    def _drawheatmap_glows_iso(self, tiles):
        """Full-diamond solid colour fill for ISO mode."""
        heat = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
        cam  = self.cam
        for n in tiles:
            col = riskcols.get(n.risklvl, (80, 80, 80))
            pts = cam.tile_diamond(n.row, n.col)
            pygame.draw.polygon(heat, (*col, 210), pts)
        self.screen.blit(heat, (0, 0))

    def _drawroadsiso(self,tiles):
        seen=set()
        prim_edges = set()
        sec_edges = set()
        if self.curtab == 1 and hasattr(self.sim.graph, 'primary_redundancy_path'):
            p1 = self.sim.graph.primary_redundancy_path
            if p1:
                for i in range(len(p1)-1): prim_edges.add(tuple(sorted([p1[i], p1[i+1]])))
            p2 = self.sim.graph.secondary_redundancy_path
            if p2:
                for i in range(len(p2)-1): sec_edges.add(tuple(sorted([p2[i], p2[i+1]])))

        for n in tiles:
            for key,e in self.sim.graph.edgemap.items():
                if not e.built: continue
                if e.src.nodeid!=n.nodeid and e.dst.nodeid!=n.nodeid: continue
                k=tuple(sorted([e.src.nodeid,e.dst.nodeid]))
                if k in seen: continue
                seen.add(k)
                x1,y1=self.cam.g2s(e.src.row,e.src.col,0)
                y1+=int(self.cam.ISO_H)
                x2,y2=self.cam.g2s(e.dst.row,e.dst.col,0)
                y2+=int(self.cam.ISO_H)
                if e.blocked:
                    # dashed red
                    dx,dy=x2-x1,y2-y1; l=max(1,math.sqrt(dx*dx+dy*dy)); steps=max(1,int(l/8))
                    for s in range(steps):
                        t1b=s/steps; t2b=(s+0.5)/steps
                        pygame.draw.line(self.screen,floodcol,(int(x1+dx*t1b),int(y1+dy*t1b)),(int(x1+dx*t2b),int(y1+dy*t2b)),3)
                    # water drop midpoint
                    mx2b=(x1+x2)//2; my2b=(y1+y2)//2
                    pygame.draw.circle(self.screen,(80,160,255),(mx2b,my2b),4)
                else:
                    pygame.draw.line(self.screen,(roadcol[0]//2,roadcol[1]//2,roadcol[2]//2),(x1,y1),(x2,y2),8)
                    pygame.draw.line(self.screen,roadcol,(x1,y1),(x2,y2),5)
                    if k in prim_edges:
                        pygame.draw.line(self.screen, (255,80,180), (x1,y1), (x2,y2), 4)
                    elif k in sec_edges:
                        pygame.draw.line(self.screen, (80,255,120), (x1,y1), (x2,y2), 4)

    def _policeshield(self,cx,cy,size,risk_level,count,pulse_t):
        """Draw a proper police shield badge at (cx,cy)."""
        risk_col={"High":(210,20,20),"Medium":(200,160,0),"Low":(0,160,60)}
        bc=risk_col.get(risk_level,(30,110,220))
        # pulsing outer glow
        pr=int(size+6+3*abs(math.sin(pulse_t)))
        gs=pygame.Surface((pr*2+4,pr*2+4),pygame.SRCALPHA)
        pygame.draw.circle(gs,(*bc,55),(pr+2,pr+2),pr); self.screen.blit(gs,(cx-pr-2,cy-pr-2))
        # shield shape: rectangle top + pointed bottom
        s2=size; pts=[
            (cx-s2,  cy-s2),   # top-left
            (cx+s2,  cy-s2),   # top-right
            (cx+s2,  cy+s2//2),# right
            (cx,     cy+s2+4), # bottom point
            (cx-s2,  cy+s2//2),# left
        ]
        pygame.draw.polygon(self.screen,bc,pts)
        pygame.draw.polygon(self.screen,(255,255,255),pts,2)
        # inner highlight stripe
        inner=[(x+2,y+2) for (x,y) in pts[:3]]+[(cx+s2-2,cy+s2//2-2),(cx,cy+s2+1),(cx-s2+2,cy+s2//2-2)]
        pygame.draw.polygon(self.screen,tuple(min(255,c+60) for c in bc),inner,1)
        # star in center (5-point)
        for i in range(5):
            ang=math.radians(-90+i*72)
            ox=cx+int((s2*0.55)*math.cos(ang)); oy=cy-2+int((s2*0.55)*math.sin(ang))
            ang2=math.radians(-90+i*72+36)
            ox2=cx+int((s2*0.25)*math.cos(ang2)); oy2=cy-2+int((s2*0.25)*math.sin(ang2))
            if i==0:
                star_pts=[(ox,oy)]
            else:
                star_pts+=[ox2,oy2,ox,oy] if False else star_pts
        # simpler star: just draw radiating lines
        for i in range(5):
            ang=math.radians(-90+i*72)
            ex=cx+int((s2*0.52)*math.cos(ang)); ey=cy-2+int((s2*0.52)*math.sin(ang))
            pygame.draw.line(self.screen,(255,255,255),(cx,cy-2),(ex,ey),1)
        pygame.draw.circle(self.screen,(255,255,255),(cx,cy-2),int(s2*0.18))
        # officer count chip (top-right corner)
        chip_x=cx+s2; chip_y=cy-s2
        chip_r=max(7,s2//2)
        pygame.draw.circle(self.screen,(20,20,20),(chip_x,chip_y),chip_r)
        pygame.draw.circle(self.screen,(255,220,50),(chip_x,chip_y),chip_r,2)
        ct=self.fnsm.render(str(count),True,(255,220,50))
        self.screen.blit(ct,(chip_x-ct.get_width()//2,chip_y-ct.get_height()//2))

    def _drawpoliceiso(self,n,count):
        """Draw a police shield badge floating above a node in ISO mode."""
        cam=self.cam; H=bldh.get(n.kind,0)
        sx,sy=cam.g2s(n.row,n.col,0); sy+=int(2*cam.ISO_H)-int(H*cam.FH)-8
        self._policeshield(sx,sy-20,9,n.risklvl,count,self.pulse)

    def _drawbldiso(self,n):
        cam=self.cam; kind=n.kind
        H=bldh.get(kind,0)
        if kind==residential: H=self.respals.get(n.nodeid,RESPAL[0]) and 1  # always 1
        FH=cam.FH; hw=cam.ISO_W*0.5; hh=cam.ISO_H*0.5
        if kind in (residential,) and n.nodeid in self.respals:
            faces=self.respals[n.nodeid]
        else:
            faces=self._bld3d(kind)
        topc,lftc,rgtc=faces
        # ambient glow for hospital and powerplant
        if kind in (hospital,powerplant) and self.nightmode:
            gx,gy=cam.g2s(n.row,n.col,0); gy+=int(hh)
            gs=pygame.Surface((80,80),pygame.SRCALPHA)
            pygame.draw.circle(gs,(*topc,20),(40,40),40)
            self.screen.blit(gs,(gx-40,gy-40))
        # ground diamond
        pts=cam.tile_diamond(n.row,n.col)
        gcol=(160,175,140) if not self.nightmode else (18,24,38)
        pygame.draw.polygon(self.screen,gcol,pts)
        pygame.draw.polygon(self.screen,(22,30,46),pts,1)
        if kind==empty or H==0: return
        # 3D box
        sx,sy=cam.g2s(n.row,n.col,0); sy+=int(2*hh)
        elev=int(H*FH)
        # left face (SW)
        lf=[(sx-hw,sy-hh),(sx,sy),(sx,sy-elev),(sx-hw,sy-hh-elev)]
        pygame.draw.polygon(self.screen,lftc,lf)
        # right face (SE)
        rf=[(sx+hw,sy-hh),(sx,sy),(sx,sy-elev),(sx+hw,sy-hh-elev)]
        pygame.draw.polygon(self.screen,rgtc,rf)
        # top face
        tf=[(sx,sy-elev-2*hh),(sx+hw,sy-elev-hh),(sx,sy-elev),(sx-hw,sy-elev-hh)]
        pygame.draw.polygon(self.screen,topc,tf)
        # edge lines
        for poly in [lf,rf,tf]:
            pygame.draw.polygon(self.screen,(0,0,0),poly,1)
        # windows on side faces (night only)
        if self.nightmode and H>=2:
            wc=(255,240,160)
            for floor in range(min(H,4)):
                wy=int(sy-floor*FH-FH*0.6); wx1=int(sx-hw*0.6); wx2=int(sx+hw*0.6)
                pygame.draw.rect(self.screen,wc,(wx1,wy-3,4,4))
                pygame.draw.rect(self.screen,wc,(wx2-4,wy-3,4,4))
        # roof details
        tx,ty=int(sx),int(sy-elev-int(hh))
        if kind==hospital:
            pygame.draw.rect(self.screen,(255,255,255),(tx-6,ty-2,12,4))
            pygame.draw.rect(self.screen,(255,255,255),(tx-2,ty-6,4,12))
        elif kind==powerplant:
            pts2=[(tx,ty-8),(tx-5,ty+2),(tx,ty-1),(tx+5,ty+2)]
            if len(pts2)>=3: pygame.draw.polygon(self.screen,(255,230,0),pts2)
        elif kind==industrial:
            for dx4 in [-4,4]:
                pygame.draw.rect(self.screen,(180,180,180),(tx+dx4-2,ty-12,4,12))
        elif kind==depot:
            pygame.draw.circle(self.screen,(255,255,255),(tx,ty),7,2)
            pygame.draw.rect(self.screen,(255,255,255),(tx-5,ty-2,10,4))
            pygame.draw.rect(self.screen,(255,255,255),(tx-2,ty-5,4,10))

    def _drawambiso(self,nodeid):
        n=self.sim.graph.nodes[nodeid]; cam=self.cam
        H=bldh.get(n.kind,0)
        sx,sy=cam.g2s(n.row,n.col,0); sy+=int(2*cam.ISO_H)-int(H*cam.FH)-4
        # pulsing halo
        pr=int(14+4*abs(math.sin(self.pulse)))
        gs=pygame.Surface((pr*2+4,pr*2+4),pygame.SRCALPHA)
        pygame.draw.circle(gs,(*ambcol,50),(pr+2,pr+2),pr); self.screen.blit(gs,(sx-pr-2,sy-pr-2))
        # box body
        w,h,d=16,10,7
        body=[(sx-w//2,sy),(sx+w//2,sy),(sx+w//2+d//2,sy-d//2),(sx-w//2+d//2,sy-d//2)]
        pygame.draw.polygon(self.screen,ambcol,body)
        # cab top
        roof=[(sx-w//4,sy-h),(sx+w//4,sy-h),(sx+w//4+d//4,sy-h-d//4),(sx-w//4+d//4,sy-h-d//4)]
        pygame.draw.polygon(self.screen,(255,240,100),roof)
        # cross on roof
        rx=sx+d//8; ry=sy-h-2
        pygame.draw.rect(self.screen,(255,50,50),(rx-4,ry-1,8,3))
        pygame.draw.rect(self.screen,(255,50,50),(rx-1,ry-4,3,8))
        # siren - alternates red/blue
        sirenon=pygame.time.get_ticks()%600<300
        pygame.draw.circle(self.screen,(255,60,60) if sirenon else (60,100,255),(sx+d//4,sy-h-d//4),3)
        # wheels
        for wx in [sx-w//4,sx+w//4]:
            pygame.draw.circle(self.screen,(40,40,40),(wx,sy+2),3)

    def _drawteamiso(self):
        tx,ty=self._teampos_lerped()
        for i,(px,py) in enumerate(reversed(self.teamtrail[-4:])):
            a=[3,8,15,25][i]; r=9
            gs=pygame.Surface((r*2+4,r*2+4),pygame.SRCALPHA)
            pygame.draw.circle(gs,(*teamcol,a),(r+2,r+2),r); self.screen.blit(gs,(px-r-2,py-r-2))
        # jeep body
        w,h,d=14,9,7
        body=[(tx-w//2,ty),(tx+w//2,ty),(tx+w//2+d//2,ty-d//2),(tx-w//2+d//2,ty-d//2)]
        pygame.draw.polygon(self.screen,teamcol,body)
        roof=[(tx-w//4,ty-h),(tx+w//4,ty-h),(tx+w//4+d//4,ty-h-d//4),(tx-w//4+d//4,ty-h-d//4)]
        pygame.draw.polygon(self.screen,(0,180,200),roof)
        pygame.draw.rect(self.screen,(255,255,255),(tx+d//8-4,ty-h-2,8,3))
        pygame.draw.rect(self.screen,(255,255,255),(tx+d//8-1,ty-h-5,3,8))
        # spinning siren
        ang=self.pulse*2; sr=8
        pygame.draw.circle(self.screen,acc2,(tx+d//4+int(math.cos(ang)*3),ty-h-d//4+int(math.sin(ang)*2)),3)

    def _drawciviso(self,n):
        cam=self.cam; H=bldh.get(n.kind,0)
        sx,sy=cam.g2s(n.row,n.col,0); sy+=int(2*cam.ISO_H)-int(H*cam.FH)-8
        # beacon beam
        a=int(100+80*abs(math.sin(self.pulse+n.nodeid)))
        bs=pygame.Surface((4,30),pygame.SRCALPHA)
        for yi in range(30): pygame.draw.line(bs,(*civcol,max(0,a-yi*3)),(0,yi),(3,yi))
        self.screen.blit(bs,(sx-2,sy-38))
        # cylinder shape
        pygame.draw.ellipse(self.screen,civcol,(sx-5,sy-3,10,5))
        pygame.draw.rect(self.screen,tuple(min(255,c+40) for c in civcol),(sx-3,sy-12,6,10))
        pygame.draw.ellipse(self.screen,civcol,(sx-3,sy-15,6,4))

    def _drawrouteiso(self):
        path=self.sim.router.getfullpath()
        if len(path)<2: return
        # outer glow pass
        for i in range(len(path)-1):
            x1,y1=self._nc(path[i]); x2,y2=self._nc(path[i+1])
            gs_r=pygame.Surface((self.W,self.H),pygame.SRCALPHA)
            pygame.draw.line(gs_r,(*rtcol,30),(x1,y1),(x2,y2),14)
            self.screen.blit(gs_r,(0,0))
        # dark shadow
        for i in range(len(path)-1):
            x1,y1=self._nc(path[i]); x2,y2=self._nc(path[i+1])
            pygame.draw.line(self.screen,(0,80,70),(x1,y1),(x2,y2),7)
        # main route line
        for i in range(len(path)-1):
            x1,y1=self._nc(path[i]); x2,y2=self._nc(path[i+1])
            pygame.draw.line(self.screen,rtcol,(x1,y1),(x2,y2),3)
        # bright center
        for i in range(len(path)-1):
            x1,y1=self._nc(path[i]); x2,y2=self._nc(path[i+1])
            pygame.draw.line(self.screen,(200,255,240),(x1,y1),(x2,y2),1)
        # direction arrows
        for i in range(0,len(path)-1,max(1,len(path)//6+1)):
            x1,y1=self._nc(path[i]); x2,y2=self._nc(path[i+1])
            mx2b=(x1+x2)//2; my2b=(y1+y2)//2; angle=math.atan2(y2-y1,x2-x1)
            for side in (-1,1):
                ax=mx2b-int(math.cos(angle-side*math.pi*0.4)*9)
                ay=my2b-int(math.sin(angle-side*math.pi*0.4)*9)
                pygame.draw.line(self.screen,(255,255,255),(ax,ay),(mx2b,my2b),2)
        # pulsing head
        t=self.routepulset; segs=len(path)-1; pos=t*segs; seg=int(pos); frac=pos-seg
        if seg<segs:
            px1,py1=self._nc(path[seg]); px2,py2=self._nc(path[seg+1])
            pdx=int(px1+(px2-px1)*frac); pdy=int(py1+(py2-py1)*frac)
            pr=int(11+5*abs(math.sin(self.pulse)))
            gs2=pygame.Surface((pr*2+6,pr*2+6),pygame.SRCALPHA)
            pygame.draw.circle(gs2,(*rtcol,90),(pr+3,pr+3),pr); self.screen.blit(gs2,(pdx-pr-3,pdy-pr-3))
            pygame.draw.circle(self.screen,rtcol,(pdx,pdy),8)
            pygame.draw.circle(self.screen,(255,255,255),(pdx,pdy),4)

    # ── FLAT 2D MAP ──────────────────────────────────────────────────
    def _drawmapflat(self):
        g=self.sim.graph; cs=self.cellsize
        # subtle scanline overlay
        sl=pygame.Surface(self.maparea.size,pygame.SRCALPHA)
        for yi in range(0,self.maparea.height,4):
            pygame.draw.line(sl,(0,0,0,18),(0,yi),(self.maparea.width,yi),1)
        self.screen.blit(sl,self.maparea.topleft)
        # grid lines
        for r in range(g.rows+1):
            yy=self.offsety+r*cs
            pygame.draw.line(self.screen,(22,28,50),(self.offsetx,yy),(self.offsetx+g.cols*cs,yy),1)
        for c in range(g.cols+1):
            xx=self.offsetx+c*cs
            pygame.draw.line(self.screen,(22,28,50),(xx,self.offsety),(xx,self.offsety+g.rows*cs),1)
        # ── route tile highlights (tab 3) ──
        if self.curtab==3 and self.sim.router and not self.sim.router.done:
            path=self.sim.router.getfullpath()
            pathset=set(path)
            for nid in pathset:
                n=self.sim.graph.nodes[nid]
                tx2=self.offsetx+n.col*cs; ty2=self.offsety+n.row*cs
                hs=pygame.Surface((cs,cs),pygame.SRCALPHA)
                a=int(35+20*abs(math.sin(self.pulse+nid*0.7)))
                pygame.draw.rect(hs,(*rtcol,a),(0,0,cs,cs),border_radius=4)
                self.screen.blit(hs,(tx2,ty2))
        # ── heatmap drawn AFTER tiles as spreading radial glow blobs ──
        if self.showheatmap or self.curtab==4:
            self._drawheatmap_glows_flat(g, cs)
        # ── ambulance coverage ──
        if self.showambcov or self.curtab==2:
            for n in g.allnodes():
                if n.ambcov:
                    s=pygame.Surface((cs,cs),pygame.SRCALPHA)
                    pygame.draw.rect(s,(0,200,100,38),(0,0,cs,cs))
                    self.screen.blit(s,(self.offsetx+n.col*cs,self.offsety+n.row*cs))
        # ── node tiles drawn FIRST so roads appear on top ──
        for n in g.allnodes():
            nx2=self.offsetx+n.col*cs; ny2=self.offsety+n.row*cs; pad=max(2,cs//10)
            col=nodecols.get(n.kind,(22,28,46))
            # drop shadow
            sha=pygame.Surface((cs,cs),pygame.SRCALPHA)
            pygame.draw.rect(sha,(0,0,0,55),(pad+2,pad+2,cs-pad*2,cs-pad*2),border_radius=max(3,cs//7))
            self.screen.blit(sha,(nx2,ny2))
            cell=pygame.Rect(nx2+pad,ny2+pad,cs-pad*2,cs-pad*2)
            pygame.draw.rect(self.screen,col,cell,border_radius=max(3,cs//7))
            # top highlight bevel
            hi=tuple(min(255,c+70) for c in col)
            pygame.draw.rect(self.screen,hi,pygame.Rect(cell.x+2,cell.y+2,cell.width-4,3),border_radius=2)
            # right-side shader
            sh2=tuple(max(0,c-40) for c in col)
            pygame.draw.rect(self.screen,sh2,pygame.Rect(cell.right-3,cell.y+4,3,cell.height-4),border_radius=2)
            if n.blocked: pygame.draw.rect(self.screen,bad,cell,2,border_radius=max(3,cs//7))
            # icon — hand drawn with pygame shapes (works on every OS, no font needed)
            if cs>=18:
                cx_i=nx2+cs//2; cy_i=ny2+cs//2; sz=max(4,cs//5)
                ic=(255,255,255)
                if n.kind==hospital:
                    # white medical cross
                    t=max(2,sz//2)
                    pygame.draw.rect(self.screen,ic,(cx_i-sz,cy_i-t,sz*2,t*2))
                    pygame.draw.rect(self.screen,ic,(cx_i-t,cy_i-sz,t*2,sz*2))
                elif n.kind==residential:
                    # house: triangle roof + rect body
                    rh=sz; rw=int(sz*1.3)
                    pygame.draw.polygon(self.screen,ic,[(cx_i,cy_i-sz-2),(cx_i-rw,cy_i-1),(cx_i+rw,cy_i-1)])
                    pygame.draw.rect(self.screen,ic,(cx_i-rw+2,cy_i,rw*2-4,rh))
                    # door
                    pygame.draw.rect(self.screen,col,(cx_i-max(1,sz//4),cy_i+1,max(2,sz//2),rh-1))
                elif n.kind==school:
                    # open book shape
                    bw=sz; bh=int(sz*0.7)
                    pygame.draw.rect(self.screen,ic,(cx_i-bw,cy_i-bh,bw,bh*2),1)
                    pygame.draw.rect(self.screen,ic,(cx_i,cy_i-bh,bw,bh*2),1)
                    pygame.draw.line(self.screen,ic,(cx_i,cy_i-bh-2),(cx_i,cy_i+bh+1),2)
                    # lines on pages
                    for dy in range(-bh+3,bh,max(3,bh//2)):
                        pygame.draw.line(self.screen,ic,(cx_i-bw+2,cy_i+dy),(cx_i-2,cy_i+dy),1)
                        pygame.draw.line(self.screen,ic,(cx_i+2,cy_i+dy),(cx_i+bw-2,cy_i+dy),1)
                elif n.kind==industrial:
                    # factory: two smokestacks + base
                    bw=int(sz*1.2); bh=sz
                    pygame.draw.rect(self.screen,ic,(cx_i-bw,cy_i,bw*2,bh))
                    sw=max(2,sz//3); sh=max(3,sz)
                    pygame.draw.rect(self.screen,ic,(cx_i-bw+2,cy_i-sh,sw,sh))
                    pygame.draw.rect(self.screen,ic,(cx_i+bw-sw-2,cy_i-sh,sw,sh))
                    # smoke puffs
                    pr=max(2,sw//2+1)
                    pygame.draw.circle(self.screen,(200,200,210),(cx_i-bw+2+sw//2,cy_i-sh-pr),pr)
                    pygame.draw.circle(self.screen,(200,200,210),(cx_i+bw-sw//2-2,cy_i-sh-pr),pr)
                elif n.kind==powerplant:
                    # lightning bolt
                    pts=[
                        (cx_i+1, cy_i-sz-3),
                        (cx_i-sz//2-1, cy_i+1),
                        (cx_i+1, cy_i+1),
                        (cx_i-1, cy_i+sz+3),
                        (cx_i+sz//2+1, cy_i-1),
                        (cx_i-1, cy_i-1),
                    ]
                    pygame.draw.polygon(self.screen,(255,230,0),pts)
                    pygame.draw.polygon(self.screen,ic,pts,1)
                elif n.kind==depot:
                    # ambulance cross inside circle
                    r=sz
                    pygame.draw.circle(self.screen,ic,(cx_i,cy_i),r,2)
                    t=max(2,r//3)
                    pygame.draw.rect(self.screen,ic,(cx_i-r+3,cy_i-t,r*2-6,t*2))
                    pygame.draw.rect(self.screen,ic,(cx_i-t,cy_i-r+3,t*2,r*2-6))
        # ── roads drawn AFTER tiles so they are always visible ──
        if self.showroads:
            seen=set()
            prim_edges = set()
            sec_edges = set()
            if self.curtab == 1 and hasattr(g, 'primary_redundancy_path'):
                p1 = g.primary_redundancy_path
                if p1:
                    for i in range(len(p1)-1): prim_edges.add(tuple(sorted([p1[i], p1[i+1]])))
                p2 = g.secondary_redundancy_path
                if p2:
                    for i in range(len(p2)-1): sec_edges.add(tuple(sorted([p2[i], p2[i+1]])))
            for key,e in g.edgemap.items():
                if not e.built: continue
                k=tuple(sorted([e.src.nodeid,e.dst.nodeid]))
                if k in seen: continue; seen.add(k)
                x1,y1=self._nc(e.src.nodeid); x2,y2=self._nc(e.dst.nodeid)
                if e.blocked:
                    dx,dy=x2-x1,y2-y1; length=max(1,math.sqrt(dx*dx+dy*dy)); steps=max(1,int(length/7))
                    for s in range(steps):
                        t1b=s/steps; t2b=(s+0.5)/steps
                        pygame.draw.line(self.screen,floodcol,(int(x1+dx*t1b),int(y1+dy*t1b)),(int(x1+dx*t2b),int(y1+dy*t2b)),4)
                    pygame.draw.circle(self.screen,(80,160,255),((x1+x2)//2,(y1+y2)//2),5)
                else:
                    # bright road drawn on top of tiles
                    pygame.draw.line(self.screen,(10,12,28),(x1,y1),(x2,y2),6)  # dark shadow
                    pygame.draw.line(self.screen,roadcol,(x1,y1),(x2,y2),4)    # main road
                    pygame.draw.line(self.screen,tuple(min(255,c+80) for c in roadcol),(x1,y1),(x2,y2),1)  # center stripe
                    if k in prim_edges:
                        pygame.draw.line(self.screen,(255,80,180),(x1,y1),(x2,y2),3)
                    elif k in sec_edges:
                        pygame.draw.line(self.screen,(80,255,120),(x1,y1),(x2,y2),3)
        # ── police shields on Crime tab (2D mode) ──
        if self.curtab==4 and self.showpolice:
            omap=self.sim.officermap
            for nid,cnt in omap.items():
                n2=g.nodes[nid]; px2,py2=self._nc(nid)
                self._policeshield(px2,py2,max(8,cs//3),n2.risklvl,cnt,self.pulse)
        # ── route overlay (drawn on top of tiles for max visibility) ──
        if self.curtab==3 and self.sim.router and not self.sim.router.done:
            self._drawrouteflat()
        # ── ambulances ──
        if self.curtab in (0,2):
            for pid in self.sim.ambplaces:
                ax2,ay2=self._nc(pid); r=max(7,cs//4)
                pr=r+int(4*abs(math.sin(self.pulse)))
                gs4=pygame.Surface((pr*2+6,pr*2+6),pygame.SRCALPHA)
                pygame.draw.circle(gs4,(*ambcol,55),(pr+3,pr+3),pr,2); self.screen.blit(gs4,(ax2-pr-3,ay2-pr-3))
                pygame.draw.circle(self.screen,ambcol,(ax2,ay2),r)
                pygame.draw.rect(self.screen,(0,0,0),(ax2-r//2,ay2-2,r,4))
                pygame.draw.rect(self.screen,(0,0,0),(ax2-2,ay2-r//2,4,r))
        # ── civilians ──
        if self.curtab in (0,3) and self.sim.router:
            for c in self.sim.civilians:
                try:
                    idx=self.sim.civilians.index(c)
                    if c.nodeid in self.sim.router.unvisited:
                        cx2,cy2=self._nc(c.nodeid); r=max(5,cs//5)
                        pr=r+int(3*abs(math.sin(self.pulse+idx)))
                        gs7=pygame.Surface((pr*2+4,pr*2+4),pygame.SRCALPHA)
                        pygame.draw.circle(gs7,(*civcol,55),(pr+2,pr+2),pr); self.screen.blit(gs7,(cx2-pr-2,cy2-pr-2))
                        pygame.draw.circle(self.screen,civcol,(cx2,cy2),r)
                        # SOS beacon
                        beam=pygame.Surface((4,cs//2),pygame.SRCALPHA)
                        for yi in range(cs//2): pygame.draw.line(beam,(*civcol,max(0,int(160*(1-yi/(cs//2)))))  ,(0,yi),(3,yi))
                        self.screen.blit(beam,(cx2-2,cy2-cs//2-r))
                except: pass
            # ── medical team ──
            if self.sim.teampos is not None:
                tx,ty=self._teampos_lerped()
                for i,(tpx,tpy) in enumerate(reversed(self.teamtrail[-4:])):
                    a=[5,12,22,35][i]; r2=max(6,cs//3)
                    gs5=pygame.Surface((r2*2+4,r2*2+4),pygame.SRCALPHA)
                    pygame.draw.circle(gs5,(*teamcol,a),(r2+2,r2+2),r2); self.screen.blit(gs5,(tpx-r2-2,tpy-r2-2))
                r=max(8,cs//3)
                gs6=pygame.Surface((r*3,r*3),pygame.SRCALPHA)
                pygame.draw.circle(gs6,(*teamcol,55),(r*3//2,r*3//2),r+6); self.screen.blit(gs6,(tx-r*3//2,ty-r*3//2))
                pygame.draw.circle(self.screen,teamcol,(tx,ty),r)
                hw=r//2
                pygame.draw.rect(self.screen,(0,0,0),(tx-hw,ty-2,hw*2,4))
                pygame.draw.rect(self.screen,(0,0,0),(tx-2,ty-hw,4,hw*2))
        for rp in self.ripples: rp.draw(self.screen)
        for pp in self.rescuepings: pp.draw(self.screen)
        for sp in self.sparkles: sp.draw(self.screen)

    def _drawrouteflat(self):
        """Enhanced route rendering for 2D mode: multi-layer glow, direction arrows, pulsing head."""
        path=self.sim.router.getfullpath()
        if len(path)<2: return
        cs=self.cellsize
        # ── pass 1: outer glow ──
        for i in range(len(path)-1):
            x1,y1=self._nc(path[i]); x2,y2=self._nc(path[i+1])
            gs=pygame.Surface((self.maparea.width,self.maparea.height),pygame.SRCALPHA)
            relx1=x1-self.maparea.x; rely1=y1-self.maparea.y
            relx2=x2-self.maparea.x; rely2=y2-self.maparea.y
            pygame.draw.line(gs,(*rtcol,28),(relx1,rely1),(relx2,rely2),14)
            self.screen.blit(gs,self.maparea.topleft)
        # ── pass 2: mid glow ──
        for i in range(len(path)-1):
            x1,y1=self._nc(path[i]); x2,y2=self._nc(path[i+1])
            pygame.draw.line(self.screen,(0,80,65),(x1,y1),(x2,y2),8)
        # ── pass 3: main route line ──
        for i in range(len(path)-1):
            x1,y1=self._nc(path[i]); x2,y2=self._nc(path[i+1])
            pygame.draw.line(self.screen,rtcol,(x1,y1),(x2,y2),4)
        # ── pass 4: bright centerline ──
        for i in range(len(path)-1):
            x1,y1=self._nc(path[i]); x2,y2=self._nc(path[i+1])
            cl=tuple(min(255,c+80) for c in rtcol)
            pygame.draw.line(self.screen,cl,(x1,y1),(x2,y2),1)
        # ── direction chevron arrows every other segment ──
        arrsz=max(7,cs//5)
        for i in range(0,len(path)-1,max(1,len(path)//8+1)):
            x1,y1=self._nc(path[i]); x2,y2=self._nc(path[i+1])
            mx2b=(x1+x2)//2; my2b=(y1+y2)//2
            angle=math.atan2(y2-y1,x2-x1)
            for side in (-1,1):
                ax=mx2b-int(math.cos(angle-side*math.pi*0.4)*arrsz)
                ay=my2b-int(math.sin(angle-side*math.pi*0.4)*arrsz)
                pygame.draw.line(self.screen,(255,255,255),(ax,ay),(mx2b,my2b),2)
        # ── waypoint dots at each path node ──
        for nid in path:
            wx,wy=self._nc(nid)
            pygame.draw.circle(self.screen,(0,60,50),(wx,wy),4)
            pygame.draw.circle(self.screen,rtcol,(wx,wy),3)
        # ── animated pulsing head along route ──
        t=self.routepulset; segs=len(path)-1
        pos=t*segs; seg=int(pos); frac=pos-seg
        if seg<segs:
            px1,py1=self._nc(path[seg]); px2,py2=self._nc(path[seg+1])
            pdx=int(px1+(px2-px1)*frac); pdy=int(py1+(py2-py1)*frac)
            pr=int(9+4*abs(math.sin(self.pulse)))
            gs2=pygame.Surface((pr*2+6,pr*2+6),pygame.SRCALPHA)
            pygame.draw.circle(gs2,(*rtcol,90),(pr+3,pr+3),pr); self.screen.blit(gs2,(pdx-pr-3,pdy-pr-3))
            pygame.draw.circle(self.screen,rtcol,(pdx,pdy),7)
            pygame.draw.circle(self.screen,(255,255,255),(pdx,pdy),4)

    # ── completion overlay ────────────────────────────────────────────
    def _drawcompletionoverlay(self):
        if not self.showcompletion: return
        ov=pygame.Surface((self.W,self.H),pygame.SRCALPHA)
        pygame.draw.rect(ov,(4,6,14,210),(0,0,self.W,self.H)); self.screen.blit(ov,(0,0))
        cx=self.W//2; cy=self.H//2-80
        pulse=int(205+50*abs(math.sin(self.pulse)))
        rescued=self.sim.router.rescuedcount if self.sim.router else 0
        title=self.fnttl.render("SIMULATION COMPLETE",True,(acc2[0],pulse,acc2[2]))
        self.screen.blit(title,(cx-title.get_width()//2,cy))
        if rescued == len(self.sim.civilians):
            subh=self.fnxl.render("Emergency routing: all civilians reached",True,(0,pulse,pulse))
        else:
            subh=self.fnxl.render(
                f"Emergency routing: {rescued}/{len(self.sim.civilians)} civilians reached",
                True,(pulse,120,120))
        self.screen.blit(subh,(cx-subh.get_width()//2,cy+42))
        lines=[f"Steps Taken: {self.sim.step} / {self.sim.maxsteps}",
               f"Civilians Rescued: {rescued} / {len(self.sim.civilians)}",
               f"Flood events: {self.totalfloods}   Emergency Reroutes: {self.totalreroutes}"]
        for i,line in enumerate(lines):
            lt=self.fnxl.render(line,True,txt); self.screen.blit(lt,(cx-lt.get_width()//2,cy+80+i*38))
        sub=self.fnsm.render("Click below to view full simulation statistics",True,dim)
        self.screen.blit(sub,(cx-sub.get_width()//2,cy+80+len(lines)*38+10))
        self.btnviewrep=pygame.Rect(cx-120,cy+80+len(lines)*38+34,240,44)
        pygame.draw.rect(self.screen,acc,self.btnviewrep,border_radius=10)
        glow=pygame.Surface((240,44),pygame.SRCALPHA)
        pygame.draw.rect(glow,(*acc2,60),(0,0,240,44),border_radius=10)
        self.screen.blit(glow,self.btnviewrep.topleft)
        vt=self.fnlg.render("VIEW STATS",True,(255,255,255))
        self.screen.blit(vt,(self.btnviewrep.x+(240-vt.get_width())//2,self.btnviewrep.y+(44-vt.get_height())//2))

    # ── stats overlay ─────────────────────────────────────────────────
    def _drawstatsoverlay(self):
        if not self.showstats: return
        ov=pygame.Surface((self.W,self.H),pygame.SRCALPHA)
        pygame.draw.rect(ov,(4,6,20,230),(0,0,self.W,self.H)); self.screen.blit(ov,(0,0))
        # panel
        pw=min(700,self.W-60); ph=min(520,self.H-60)
        px=(self.W-pw)//2; py=(self.H-ph)//2
        pygame.draw.rect(self.screen,(10,14,32),(px,py,pw,ph),border_radius=16)
        pygame.draw.rect(self.screen,acc,(px,py,pw,ph),2,border_radius=16)
        # title bar
        pygame.draw.rect(self.screen,(18,28,68),(px,py,pw,48),border_radius=16)
        title=self.fnxl.render("SIMULATION STATISTICS",True,acc)
        self.screen.blit(title,(px+(pw-title.get_width())//2,py+10))
        # ── stat data ──
        st=self.sim.statusdict() if self.setupdone else {}
        rescued=self.sim.router.rescuedcount if self.sim.router else 0
        nodes=list(self.sim.graph.allnodes()) if self.setupdone else []
        blk=sum(1 for n in nodes if n.blocked)
        rcnts={"High":0,"Medium":0,"Low":0}
        for n in nodes: rcnts[n.risklvl]=rcnts.get(n.risklvl,0)+1
        route=self.sim.router.getfullpath() if self.sim.router else []
        cards=[
            ("Steps Taken",      f"{self.sim.step} / {self.sim.maxsteps}",      acc),
            ("Civilians Rescued",f"{rescued} / {len(self.sim.civilians)}",      good if rescued==len(self.sim.civilians) else warn),
            ("Total Floods",     str(self.totalfloods),                          bad  if self.totalfloods>0 else good),
            ("Reroutes",         str(self.totalreroutes),                        warn if self.totalreroutes>0 else good),
            ("Road Network Cost",st.get("roadcost","N/A"),                      acc),
            ("Max Amb. Dist",    st.get("maxdist","N/A"),                       acc2),
            ("Blocked Roads",    str(blk),                                       bad  if blk>0 else good),
            ("Amb. Coverage",    f"{self.statcovpct*100:.0f}%",                  good if self.statcovpct>0.8 else warn),
            ("Route Length",     f"{len(route)} nodes",                          acc),
            ("High Risk Zones",    str(rcnts['High']),                              bad),
            ("Medium Risk",        str(rcnts['Medium']),                            warn),
            ("Low Risk Zones",     str(rcnts['Low']),                               good),
            ("CSP Violations",   str(st.get('violations',0)),                    good if st.get('violations',0)==0 else warn),
        ]
        # draw 3-column grid cards
        cols3=3; cw3=(pw-40)//cols3; ch3=70; gx=px+16; gy=py+60
        for i,(lbl,val,col) in enumerate(cards):
            ci=i%cols3; row3=i//cols3
            cx3=gx+ci*(cw3+6); cy3=gy+row3*(ch3+6)
            pygame.draw.rect(self.screen,(18,26,52),(cx3,cy3,cw3,ch3),border_radius=8)
            pygame.draw.rect(self.screen,col,(cx3,cy3,cw3,ch3),1,border_radius=8)
            lb=self.fnsm.render(lbl,True,dim)
            vl=self.fnxl.render(str(val)[:12],True,col)
            self.screen.blit(lb,(cx3+8,cy3+8))
            self.screen.blit(vl,(cx3+8,cy3+28))
        # event log summary
        logy=gy+math.ceil(len(cards)/cols3)*(ch3+6)+8
        sep=pygame.Rect(px+16,logy,pw-32,1); pygame.draw.rect(self.screen,pbdr,sep)
        logy+=8
        self.screen.blit(self.fnsm.render("LAST EVENTS:",True,dim),(px+16,logy)); logy+=16
        log=self.sim.eventlog or []
        for msg in log[-5:]:
            ml=msg.lower()
            if "flood" in ml: c=bad
            elif "replan" in ml or "route" in ml: c=warn
            elif "rescue" in ml or "reached" in ml or "mission" in ml: c=good
            else: c=dim
            ev=self.fnsm.render(msg[:70],True,c)
            self.screen.blit(ev,(px+16,logy)); logy+=15
        # buttons
        bty=py+ph-52; bx_close=px+pw-200; bx_reset=px+16
        self.btnstatsreset=pygame.Rect(bx_reset,bty,160,38)
        self.btnstatsclose=pygame.Rect(bx_close,bty,160,38)
        mx2,my2=pygame.mouse.get_pos()
        for rect,col2,label in [(self.btnstatsreset,bad,"RESET & PLAY AGAIN"),(self.btnstatsclose,acc,"CLOSE")]:
            hov=rect.collidepoint(mx2,my2)
            bc=tuple(min(255,c+40) for c in col2) if hov else col2
            pygame.draw.rect(self.screen,(30,14,14) if col2==bad else (14,28,56),rect,border_radius=8)
            pygame.draw.rect(self.screen,bc,rect,2,border_radius=8)
            if hov:
                gs=pygame.Surface(rect.size,pygame.SRCALPHA)
                pygame.draw.rect(gs,(*bc,25),(0,0,rect.width,rect.height),border_radius=8)
                self.screen.blit(gs,rect.topleft)
            lt=self.fnmd.render(label,True,txt)
            self.screen.blit(lt,(rect.x+(rect.width-lt.get_width())//2,rect.y+(rect.height-lt.get_height())//2))

    # ── shortcuts ─────────────────────────────────────────────────────
    def _drawshortcuts(self):
        if not self.showshortcuts: return
        sw=440; sh=300; sx=(self.W-sw)//2; sy=self.H-sh-self.botH-10
        pygame.draw.rect(self.screen,panelbg,(sx,sy,sw,sh),border_radius=10)
        pygame.draw.rect(self.screen,acc,(sx,sy,sw,sh),2,border_radius=10)
        self.screen.blit(self.fnlg.render("KEYBOARD SHORTCUTS  [F1 to close]",True,acc),(sx+15,sy+12))
        keys=[("Space","Next Step"),("A","Toggle Auto-Play"),("S","Cycle Speed"),
              ("R  R","Reset (double press)"),("1-5","Switch Tabs"),("H","Toggle Heatmap"),
              ("C","Toggle Ambulance Cov"),("Tab","Toggle 3D / 2D"),("N","Toggle Night / Day"),
              ("F","Fit City in View")]
        for i,(k,desc) in enumerate(keys):
            y2=sy+36+i*26
            pygame.draw.rect(self.screen,(22,30,58),(sx+12,y2,sw-24,22),border_radius=5)
            ks=self.fnmd.render(f"[{k}]",True,acc2); ds=self.fnsm.render(desc,True,txt)
            self.screen.blit(ks,(sx+20,y2+3)); self.screen.blit(ds,(sx+120,y2+5))

    # ── hover tooltip ─────────────────────────────────────────────────
    def _drawhover(self):
        if self.hovnode:
            n=self.hovnode
            off_cnt=self.sim.officermap.get(n.nodeid,0) if self.setupdone else 0
            lines=[f"Node {n.nodeid}  ({n.row},{n.col})",f"Type:    {n.kind}",
                   f"Risk:    {n.risklvl}",f"Cluster: {n.cluster}",f"Density: {n.density:.1f}"]
            if off_cnt: lines.append(f"Officers: {off_cnt} deployed here")
            if n.blocked: lines.append("!! BLOCKED !!")
            pad=10; lh=18; bw2=200; bh2=len(lines)*lh+pad*2+20
            mx2=min(self.mousex+18,self.W-bw2-4); my2=min(self.mousey+18,self.H-bh2-4)
            pygame.draw.rect(self.screen,(10,14,32),(mx2,my2,bw2,bh2),border_radius=8)
            pygame.draw.rect(self.screen,acc,(mx2,my2,bw2,bh2),1,border_radius=8)
            for i,line in enumerate(lines):
                c=bad if "BLOCKED" in line else (txt if i==0 else dim)
                self.screen.blit(self.fnsm.render(line,True,c),(mx2+pad,my2+pad+i*lh))
            by2=my2+pad+len(lines)*lh+4; barw=bw2-pad*2; bpct=min(1.0,n.density/150.0)
            pygame.draw.rect(self.screen,(20,28,55),(mx2+pad,by2,barw,8),border_radius=4)
            pygame.draw.rect(self.screen,acc2,(mx2+pad,by2,int(barw*bpct),8),border_radius=4)
        elif self.hovedge and self.showroads and not self.isomode:
            e=self.hovedge; cost=f"{e.cost:.2f}" if not e.blocked else "FLOODED"
            lt=self.fnsm.render(f"Road cost: {cost}",True,txt)
            bw2=lt.get_width()+20; bh2=28
            mx2=min(self.mousex+14,self.W-bw2-4); my2=min(self.mousey+14,self.H-bh2-4)
            pygame.draw.rect(self.screen,(10,14,32),(mx2,my2,bw2,bh2),border_radius=6)
            pygame.draw.rect(self.screen,acc,(mx2,my2,bw2,bh2),1,border_radius=6)
            self.screen.blit(lt,(mx2+10,my2+7))
