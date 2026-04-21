#include <stdint.h>

__sfr __at 0x00 PORT_LATCH;
__sfr __at 0x04 PORT_A_ADDR;
__sfr __at 0x05 PORT_A_DATA;
__sfr __at 0x06 PORT_B_ADDR;
__sfr __at 0x07 PORT_B_DATA;
__sfr __at 0x18 PORT_NMI_EN;
__sfr __at 0x0C PORT_TO_68K;

static volatile uint8_t cmd_q[16];
static volatile uint8_t cmd_w, cmd_r;
static uint8_t playing;
static const uint8_t *sptr;
static const uint8_t *sloop;
static uint16_t delta;
static uint8_t fm_inst[4];

#define SFXTBL  ((const uint8_t *)0x0800)
#define FTBL    ((const uint8_t *)0x0A00)
#define HDR     ((const uint8_t *)0x0C00)

static void ya(uint8_t r, uint8_t v) { PORT_A_ADDR=r; PORT_A_DATA=v; }
static void yb(uint8_t r, uint8_t v) { PORT_B_ADDR=r; PORT_B_DATA=v; }

static void silence(void) {
    ya(0x07,0x3F); ya(0x08,0); ya(0x09,0); ya(0x0A,0);
    ya(0x28,0x01); ya(0x28,0x02); ya(0x28,0x05); ya(0x28,0x06);
    yb(0x00,0xBF); ya(0x10,0x01); ya(0x10,0x80);
}

static const uint8_t fmk[] = {0x01,0x02,0x05,0x06};
static const uint8_t fmp[] = {0,0,1,1};
static const uint8_t fms[] = {1,2,1,2};

static void ych(uint8_t c,uint8_t r,uint8_t v) {
    if(fmp[c]) yb(r,v); else ya(r,v);
}

static void fm_patch(uint8_t c, uint8_t id) {
    const uint8_t *p;
    uint8_t ni = HDR[0];
    uint8_t o, s, b;
    if(id==fm_inst[c]) return;
    fm_inst[c]=id;
    p = HDR + 4 + (uint16_t)id * 30;
    s = fms[c];
    for(o=0;o<4;o++) {
        b=o*4+s;
        ych(c,0x30+b,*p++); ych(c,0x40+b,*p++);
        ych(c,0x50+b,*p++); ych(c,0x60+b,*p++);
        ych(c,0x70+b,*p++); ych(c,0x80+b,*p++);
        ych(c,0x90+b,*p++);
    }
    ych(c,0xB0+s,*p);
}

static void fm_freq(uint8_t c, uint8_t note) {
    const uint8_t *f = FTBL + (uint16_t)note * 2;
    uint8_t s = fms[c];
    ych(c,0xA0+s,f[0]); ych(c,0xA4+s,f[1]);
}

static uint16_t rd_delta(void) {
    uint8_t b = *sptr++;
    if(b & 0x80) return ((uint16_t)(b&0x7F)<<7) | *sptr++;
    return b;
}

static void proc_ev(uint8_t e) {
    uint8_t c,n,v,s;
    const uint8_t *p;
    uint8_t ni=HDR[0], ns=HDR[1], np=HDR[2];

    if(e<=0x03) { ya(0x28,fmk[e]); }
    else if(e>=0x10 && e<=0x13) {
        c=e-0x10; n=*sptr++; v=*sptr++;
        (void)v; fm_freq(c,n); ya(0x28,0xF0|fmk[c]);
    }
    else if(e>=0x20 && e<=0x23) { c=e-0x20; s=*sptr++; fm_patch(c,s); }
    else if(e>=0x30 && e<=0x35) {
        c=e-0x30; s=*sptr++; v=*sptr++;
        p = HDR + 4 + (uint16_t)ni*30 + (uint16_t)s*4;
        yb(0x00, 0x80|(1<<c));
        yb(0x08+c, 0xC0|v);
        yb(0x10+c, p[0]); yb(0x18+c, p[1]);
        yb(0x20+c, p[2]); yb(0x28+c, p[3]);
        yb(0x00, 1<<c);
    }
    else if(e>=0x40 && e<=0x45) { yb(0x00, 0x80|(1<<(e-0x40))); }
    else if(e==0x50) {
        s=*sptr++;
        p = HDR + 4 + (uint16_t)ni*30 + (uint16_t)ns*4 + (uint16_t)s*7;
        ya(0x10,0x80); ya(0x11,0xC0);
        ya(0x12,p[0]); ya(0x13,p[1]);
        ya(0x14,p[2]); ya(0x15,p[3]);
        ya(0x19,p[4]); ya(0x1A,p[5]);
        ya(0x1B,p[6]); ya(0x10,0x01);
    }
    else if(e==0x51) { ya(0x10,0x00); ya(0x10,0x80); }
}

static void music_tick(void) {
    if(delta>0) { delta--; return; }
    do {
        uint8_t ev = *sptr++;
        if(ev==0xFF) {
            if(sloop) { sptr=sloop; delta=rd_delta(); }
            else playing=0;
            return;
        }
        proc_ev(ev);
        delta = rd_delta();
    } while(delta==0);
}

static void cmd_play(uint8_t t) {
    uint8_t ni=HDR[0], ns=HDR[1], np=HDR[2], nt=HDR[3];
    const uint8_t *tt;
    uint16_t so, lo;
    if(t>=nt) return;
    silence();
    tt = HDR + 4 + (uint16_t)ni*30 + (uint16_t)ns*4 + (uint16_t)np*7;
    so = tt[t*4] | ((uint16_t)tt[t*4+1]<<8);
    lo = tt[t*4+2] | ((uint16_t)tt[t*4+3]<<8);
    sptr = HDR + so;
    sloop = (lo!=0xFFFF) ? HDR + lo : 0;
    fm_inst[0]=fm_inst[1]=fm_inst[2]=fm_inst[3]=0xFF;
    delta = rd_delta();
    playing = 1;
}

static void cmd_sfx(uint8_t id) {
    const uint8_t *p = SFXTBL + (uint16_t)id*4;
    yb(0x00,0x90); yb(0x01,0x3F); yb(0x0C,0xDF);
    yb(0x14,p[0]); yb(0x1C,p[1]); yb(0x24,p[2]); yb(0x2C,p[3]);
    yb(0x00,0x10);
}

static void proc_cmds(void) {
    while(cmd_r!=cmd_w) {
        uint8_t c=cmd_q[cmd_r&0x0F]; cmd_r++;
        if(c==0x70) { playing=0; silence(); }
        else if(c>=0x80 && c<=0x8F) cmd_play(c-0x80);
        else if(c>=0x01 && c<=0x3F) cmd_sfx(c-1);
        else if(c==0x40) yb(0x00,0xBF);
    }
}

void z80_init(void) {
    cmd_w=cmd_r=0; playing=0;
    ya(0x26,0xC6); ya(0x27,0x3A);
    PORT_NMI_EN=1;
}

void z80_timer_isr(void) {
    ya(0x27,0x3A);
    proc_cmds();
    if(playing) music_tick();
}

void z80_nmi(void) {
    uint8_t c=PORT_LATCH;
    if(!c){PORT_LATCH=0;return;}
    cmd_q[cmd_w&0x0F]=c; cmd_w++;
    PORT_TO_68K=c|0x80; PORT_LATCH=0;
}
