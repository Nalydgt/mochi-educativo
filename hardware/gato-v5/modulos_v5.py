"""Front camera, removable boost cradle and replaceable slide-switch cassette.

New module solids are labelled design allowances, not vendor mechanical CAD.
"""
import math,itertools
from mathutils import Vector

def build(g,front,back,outer,battery_tray,ivory,pink,steel):
    c=g.c;B=g.BOTTOM
    parts=[];assembly=[];keepouts=[];visuals=[];hardware=[]
    def rect(name,w,h,r,z0,z1,xy):
        o=c.rounded_prism(name,w,h,r,z0,z1);o.location.x,o.location.y=xy;return o
    def bore(obj,diam,z0,z1,xy):g.boolean(obj,g.cylinder('Paso '+str(diam),diam,z0,z1,xy))
    def addpart(o,name,material,active=True):
        parts.append((o,name,material))
        if active:assembly.append(o)
        else:o.hide_render=True;o.hide_set(True)
        return o
    def rear_post(xy,top,nut_bottom,nut_top,hole_end):
        g.union(back,g.cylinder('Pilar M2 posterior',8,B+0.8,top,xy))
        bore(back,2.4,hole_end,top+0.1,xy)
        g.side_nut_trap(back,xy,4.2,nut_bottom,nut_top,2.4)
    def bolt(name,xy,z0,z1,head0,head1):
        o=g.cylinder(name,2,z0,z1,xy,vertices=48)
        g.union(o,g.cylinder('Cabeza M2',3.8,head0,head1,xy,vertices=64))
        g.finish(o,steel);hardware.append(o);return o

    # The battery tray lifts out before installing the boost and its screws.
    # Three tabs clamp onto independent metal nuts, with the bearing lips
    # ABOVE these pockets because the screws enter from +Z.
    battery_mounts=[(-37,-13),(38,0),(12,28)]
    for xy in battery_mounts:
        g.union(battery_tray,g.cylinder('Oreja bandeja bateria',8,10,12,xy))
        bore(battery_tray,2.4,9,13,xy)
        v=Vector((xy[0],xy[1]-g.CENTER_Y,0));r=v.length;v.normalize()
        length=g.W/2-r+6
        center=Vector((xy[0],xy[1],8.5))+v*(length/2-4)
        arm=g.cube('Brazo apoyo bandeja desmontable',(length,7,3),center)
        arm.rotation_euler.z=math.atan2(v.y,v.x)
        g.boolean(arm,outer,'INTERSECT',discard=False);g.union(back,arm)
        g.union(back,g.cylinder('Tuerca bandeja bateria',7,3.8,10,xy))
        bore(back,2.4,5.5,10.1,xy)
        g.side_nut_trap(back,xy,4.2,6.1,8,2.4)
        bolt('REF M2x6 bandeja bateria',xy,6,12,12,14)
        bore(battery_tray,4.4,12,16,xy)
    # Previously these interfaces were united in one rear part. A removable
    # tray needs positive clearance to the wall, closure towers and speaker.
    tray_envelope=c.ellipse_prism('Holgura bandeja contra pared',g.W-2*g.WALL-0.6,g.H-2*g.WALL-0.6,9,17)
    tray_envelope.location.y=g.CENTER_Y
    g.boolean(battery_tray,tray_envelope,'INTERSECT')
    for xy in g.SCREWS:bore(battery_tray,10.8,9,17,xy)
    for sign in (-1,1):g.boolean(battery_tray,g.cube('Despeje guia altavoz',(10.8,2.8,17.3),(-44,sign*15,15.75),0.2))
    addpart(battery_tray,'17_bandeja_bateria.stl',ivory)

    # A rounded forehead houses the whole compact board above the display.
    forehead=rect('Frente suave para camara',58,39,12,44,61.6,(0,44))
    edge=forehead.modifiers.new('Transicion redonda frente','BEVEL')
    edge.width=3;edge.segments=10;edge.limit_method='ANGLE'
    c.apply(forehead,edge)
    g.union(front,forehead)
    g.boolean(front,g.cube('Reserva interior camara',(49,30,31.6),(0,44,42.9),0.3))
    bore(front,23.4,58.2,64,(0,44))
    for x in (-15,15):bore(front,1.7,58.9,61.9,(x,44))
    carrier=rect('11 Bandeja camara frontal',46,33,4,45,47.4,(0,44))
    g.boolean(carrier,rect('Ventana posterior pines camara',38.8,25.8,2,44,49,(0,44)))
    for sign in (-1,1):
        xy=(sign*29.5,44)
        g.union(carrier,rect('Oreja corredera camara',10,12,2,45,47.4,xy))
        g.union(carrier,g.cube('Puente oreja camara',(12,5,2.4),(sign*26,44,46.2)))
        g.boolean(carrier,rect('Ranura ajuste camara',9,2.6,1.3,44,49,xy))
        g.union(front,g.cylinder('Pilar frontal camara',7,47.4,58,xy))
        bore(front,2.4,47.3,54,xy)
        g.side_nut_trap(front,xy,4.2,49.4,51.3,2.4)
        washer=g.cylinder('REF Arandela camara',6,44.5,45,xy)
        bore(washer,2.2,44,46,xy);g.finish(washer,steel);hardware.append(washer)
        bolt('REF M2x8 camara',xy,44.5,52.5,42.5,44.5)
        for yy in (34,54):g.boolean(carrier,rect('Paso cinta camara',2,8.5,0.6,44,49,(sign*21,yy)))
    addpart(carrier,'11_bandeja_camara_frontal.stl',ivory)
    cap=rect('12 Adaptador objetivo frontal',36,28,8,61.6,63.2,(0,44))
    g.union(cap,g.cylinder('Cuello optica',22.8,58.9,61.8,(0,44)))
    for x in (-15,15):bore(cap,2.4,58,64,(x,44))
    blank=g.dup(cap,'13 Adaptador optico sin perforar')
    bore(cap,20,58,65,(0,44))
    addpart(cap,'12_adaptador_objetivo_20mm.stl',pink)
    addpart(blank,'13_adaptador_objetivo_ciego.stl',ivory,False)
    for x in (-15,15):
        # Only exposed lengths are used for collision checks; the M2 threads
        # intentionally form their female threads in the printed pilot.
        bolt('REF Tramo libre M2x4 optica',(x,44),61.6,63.2,63.2,65.2)

    # MT3608: a serviceable cradle below the battery, with two millimetres
    # between the design component envelope and the battery tray underside.
    boost=rect('14 Bandeja MT3608',42,24,3,-11,-9,(0,-5))
    rail=rect('Borde MT3608',42,24,3,-9.2,-6,(0,-5))
    g.boolean(rail,rect('Interior MT3608',38.6,20.6,0.3,-10,-5,(0,-5)))
    g.union(boost,rail)
    for yy,bridge_y in [(-23,-19),(13,9)]:
        xy=(0,yy)
        g.union(boost,g.cylinder('Oreja soporte MT3608',8,-11,-9,xy))
        g.union(boost,g.cube('Puente MT3608',(5,10,2),(0,bridge_y,-10)))
        bore(boost,2.4,-12,-8,xy)
        rear_post(xy,-11,-14.9,-13,-15.5)
        bolt('REF M2x6 MT3608',xy,-15,-9,-9,-7)
    for xx in (-12,12):
        for yy in (-15.2,5.2):g.boolean(boost,rect('Paso cinta MT3608',8.5,1.6,0.4,-12,-5,(xx,yy)))
    for yy in (-8,-2):g.boolean(boost,rect('Ventilacion bandeja',14,2,0.8,-12,-8,(0,yy)))
    addpart(boost,'14_bandeja_MT3608.stl',ivory)
    for yy in (-11,-7,-3,1):g.boolean(back,rect('Ventilacion trasera',18,1.8,0.8,B-2,-10.8,(0,yy)))

    # A swappable rear cassette carries the unknown SS12D00 suffix. Its
    # terminals and solder joints stay outside the battery and boost bay.
    sx,sy=32,-5
    pad=rect('Apoyo plano cassette',34,26,4,B,B+5,(sx,sy))
    g.union(back,pad)
    g.boolean(back,rect('Hueco cassette',18.8,20.8,2,B-2,-8.2,(sx,sy)))
    for xx in (20,44):
        g.union(back,g.cylinder('Tuerca cassette',7,B+0.1,-11.7,(xx,sy)))
        bore(back,2.4,B-2,-11,(xx,sy))
        g.side_nut_trap(back,(xx,sy),4.2,-13.6,-11.7,2.4)
    cassette=rect('15 Cassette SS12D00',32,24,3,-19.6,-18,(sx,sy))
    bodyframe=rect('Cuna interruptor',14,18,2,-18,-11.7,(sx,sy))
    g.boolean(bodyframe,rect('Bolsillo cuerpo SS12D00',9.5,5,0.4,-16.2,-10,(sx,sy)))
    g.union(cassette,bodyframe)
    g.boolean(cassette,rect('Ranura actuador',6.6,3,0.8,-21,-15.7,(sx,sy)))
    g.boolean(cassette,rect('Rebaje para dedo',12,7,2,-21,-18.6,(sx,sy)))
    for yy in (-11,1):bore(cassette,1.7,-17,-11.5,(sx,yy))
    for xx in (20,44):
        bore(cassette,2.4,-21,-17,(xx,sy))
        bolt('REF M2x8 cassette',(xx,sy),-19.6,-11.6,-21.6,-19.6)
    cover=rect('16 Retenedor SS12D00',14,18,2,-11.7,-9.7,(sx,sy))
    g.boolean(cover,rect('Paso terminales SS12D00',7.5,3,0.6,-13,-8,(sx,sy)))
    for yy in (-11,1):
        bore(cover,2.4,-13,-8,(sx,yy))
        bolt('REF Tramo libre M2x6 retenedor',(sx,yy),-11.7,-9.7,-9.7,-7.7)
    addpart(cassette,'15_cassette_SS12D00.stl',ivory)
    addpart(cover,'16_retenedor_SS12D00.stl',pink)

    # Any added support is followed by a final recut of the structural bores.
    for xy in g.SCREWS:
        bore(back,3.4,B-2,g.SPLIT+0.1,xy)
        bore(back,6.8,B-2,B+9.4,xy)
    # The forehead overlaps the top edge of the round screen seat and ring.
    # Restore those interfaces after the union; preserve the exact bearing
    # plane of the carrier pillars and the full 0.35 mm glass clearance.
    bore(front,45,25,g.DEPTH+3,(0,0))
    bore(front,49.66,25,g.GLASS_Z,(0,0))
    g.boolean(front,g.cube('Despeje aro superior Waveshare',(60,3.6,g.INSERT_Z-g.BRACKET_Z+0.3),(0,25.5,(g.INSERT_Z+g.BRACKET_Z-0.3)/2)))
    for xy in g.POSTS:
        bore(front,2.4,g.INSERT_Z-0.1,g.DEPTH-5.2,xy)
        g.side_nut_trap(front,xy,4.2,g.INSERT_Z+2,g.INSERT_Z+3.9,2.4)
    slide_clearance=rect('Despeje barrido bandeja camara',52.6,33.6,4.3,44.7,47.4,(0,44))
    for sign in (-1,1):
        g.union(slide_clearance,rect('Despeje oreja corredera',16.6,12.6,2.3,44.7,47.4,(sign*29.5,44)))
        g.union(slide_clearance,g.cube('Despeje puente corredera',(18.6,5.6,2.7),(sign*26,44,46.05)))
    g.boolean(front,slide_clearance)
    for x in (-29.5,29.5):bore(front,8,41.5,45,(x,44))

    pcb=g.cube('ENV Camara PCB nominal',(40,27,1.6),(0,44,48.2))
    headers=g.cube('ENV Camara espacio posterior provisional',(38,23,20),(0,44,37.4))
    camfront=g.cube('ENV Camara componentes frontales provisionales',(42,29,9.4),(0,44,53.7))
    mt=g.cube('ENV MT3608 provisional',(38,20,17),(0,-5,-0.5))
    wires=g.cube('ENV Cables MT3608',(48,8,4),(0,-5,6))
    switch=g.cube('ENV SS12D00 nominal',(8.5,3.6,3.5),(32,-5,-14.45))
    pin=g.cube('ENV Terminales SS12D00',(5.6,1.2,5),(32,-5,-10.2))
    knob=g.cube('ENV Actuador SS12D00',(1.5,1.5,3),(32,-5,-17.7))
    keepouts.extend([pcb,headers,camfront,mt,wires,switch,pin,knob])
    for o in keepouts:o.hide_render=True
    green=g.mat('PCB camara ilustrativa',(0.02,0.15,0.09),0.65)
    blue=g.mat('PCB elevador ilustrativa',(0.025,0.12,0.32),0.6)
    dark=g.mat('Optica y componentes',(0.012,0.018,0.022),0.3)
    for name,size,loc,material in [
        ('REF PCB camara aproximada',(40,27,1.6),(0,44,48.2),green),
        ('REF Modulo ESP32 aproximado',(18,15,3),(0,45,50.5),steel),
        ('REF PCB elevador aproximada',(36,17,1.2),(0,-5,-8.4),blue),
        ('REF Inductor aproximado',(8,8,5),(-9,-5,-5.3),dark),
        ('REF Trimmer aproximado',(12,5,10),(9,-5,-2.8),blue),
        ('REF Cuerpo SS12D00 aproximado',(8.5,3.6,3.5),(32,-5,-14.45),steel),
        ('REF Mando SS12D00 aproximado',(1.5,1.5,3),(31,-5,-17.7),dark),
    ]:visuals.append(g.finish(g.cube(name,size,loc,0.2),material))
    lens=g.finish(g.cylinder('REF Objetivo frontal ilustrativo',12,57.8,62.8,(0,44)),dark)
    visuals.append(lens)
    for o in hardware:o.hide_render=False
    metadata={'camera':g.P['camera'],'boost':g.P['boost'],'switch':g.P['switch'],
        'nut_load_paths':{
            'camera_tray':{'bearing_z':49.4,'pocket_z':[49.4,51.3],'shoulder_z':[47.4,49.4],'bolt':'M2x8 plus 0.5 mm washer','head_z':44.5,'tip_z':52.5,'force_direction':[0,0,-1]},
            'boost_tray':{'bearing_z':-13,'pocket_z':[-14.9,-13],'shoulder_z':[-13,-11],'bolt':'M2x6','head_z':-9,'tip_z':-15,'force_direction':[0,0,1]},
            'switch_cassette':{'bearing_z':-13.6,'pocket_z':[-13.6,-11.7],'shoulder_z':[-15.6,-13.6],'bolt':'M2x8','head_z':-19.6,'tip_z':-11.6,'force_direction':[0,0,-1]},
            'battery_tray':{'centers':battery_mounts,'bearing_z':8,'pocket_z':[6.1,8],'shoulder_z':[8,10],'bolt':'M2x6','head_z':12,'tip_z':6,'force_direction':[0,0,1]},
        },
        'optic_screws':{'type':'M2x4 self-tapping into printed 1.7 mm pilot','head_z':63.2,'tip_z':59.2,'pilot_end_z':58.9},
        'battery_air_gap_over_boost_mm':2,
        'scope':'New module sizes and positions are design allowances, not manufacturer-STEP fit certification. Camera optical axis, headers, flex length, FOV and switch variant require physical verification.'}
    return {'parts':parts,'assembly':assembly,'keepouts':keepouts,'hardware':hardware,'camera_carrier':carrier,'camera_keepouts':[pcb,headers,camfront],'other_keepouts':[mt,wires,switch,pin,knob],
        'hide_for_interior':[cap,*[o for o in visuals if 'Objetivo' in o.name]],'metadata':metadata}

def check(self,added,front,back,bracket,battery,antenna,speaker,adapter):
    g=self
    static=[front,back,bracket,battery,antenna,speaker,adapter]
    for o in added['assembly']:
        for s in static:g.collision(o,s,label='V5 added printed part vs existing assembly')
    for a,b in itertools.combinations(added['assembly'],2):g.collision(a,b,label='V5 added printed parts')
    for hw in added['hardware']:
        for s in [front,back,bracket,*added['assembly'],battery,antenna,speaker,adapter]:g.collision(hw,s,label='V5 bolt exposed lengths and captured fasteners')
    for o in added['other_keepouts']:
        for s in static+added['assembly']:g.collision(o,s,label='V5 provisional module envelope')
    # The stationary board and its tray share a support face; the assumed
    # rear header envelope must pass through the open middle of the tray.
    for o in added['camera_keepouts']:g.collision(o,added['camera_carrier'],label='camera board/header vs tray')
    for move in (-3,0,3):
        for obj in [added['camera_carrier'],*added['camera_keepouts']]:
            temp=g.dup(obj,'TEMP Camera slide '+str(move));temp.location.x+=move
            for s in static+[o for o in added['assembly'] if o!=added['camera_carrier']]:g.collision(temp,s,label='front camera tray and provisional board sweep')
            for hw in added['hardware']:g.collision(temp,hw,label='camera slide vs fixed fasteners')
            g.bpy.data.objects.remove(temp,do_unlink=True)
    knob=added['other_keepouts'][-1]
    for travel in (-1,0,1):
        temp=g.dup(knob,'TEMP Slider sweep');temp.location.x+=travel
        for s in static+added['assembly']:g.collision(temp,s,label='SS12D00 nominal 2 mm slider sweep')
        g.bpy.data.objects.remove(temp,do_unlink=True)
    added['metadata']['camera_slide_checked_x_mm']=[-3,0,3]
    added['metadata']['switch_slide_checked_x_mm']=[-1,0,1]
