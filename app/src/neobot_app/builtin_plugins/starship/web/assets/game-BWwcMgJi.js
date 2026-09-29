import{D as vu,P as dt,l as xu,Q as Vs,a as _u,b as yu,g as hs,c as Mu,s as bu,d as wu,e as Su}from"./index-BQVcQ7rm.js";/**
 * @license
 * Copyright 2010-2024 Three.js Authors
 * SPDX-License-Identifier: MIT
 */const Ga="169",qi={ROTATE:0,DOLLY:1,PAN:2},Wi={ROTATE:0,PAN:1,DOLLY_PAN:2,DOLLY_ROTATE:3},Tu=0,Sl=1,Eu=2,lh=1,ch=2,Un=3,wn=0,Ht=1,Dt=2,kn=0,Qn=1,Mn=2,Tl=3,El=4,Au=5,ui=100,Cu=101,Pu=102,Ru=103,Du=104,Iu=200,Lu=201,Nu=202,Uu=203,Yo=204,qo=205,Ou=206,Fu=207,zu=208,ku=209,Bu=210,Vu=211,Hu=212,Gu=213,Wu=214,jo=0,Ko=1,Zo=2,Ji=3,Jo=4,$o=5,Qo=6,ea=7,hh=0,Xu=1,Yu=2,ei=0,uh=1,dh=2,fh=3,Wr=4,qu=5,ph=6,mh=7,gh=300,$i=301,Qi=302,Dr=303,ta=304,Xr=306,na=1e3,fi=1001,ia=1002,$t=1003,ju=1004,Hs=1005,Ct=1006,so=1007,pi=1008,Vn=1009,vh=1010,xh=1011,Ds=1012,Wa=1013,gi=1014,Tn=1015,bn=1016,Xa=1017,Ya=1018,es=1020,_h=35902,yh=1021,Mh=1022,sn=1023,bh=1024,wh=1025,ji=1026,ts=1027,qa=1028,ja=1029,Sh=1030,Ka=1031,Za=1033,wr=33776,Sr=33777,Tr=33778,Er=33779,sa=35840,ra=35841,oa=35842,aa=35843,la=36196,ca=37492,ha=37496,ua=37808,da=37809,fa=37810,pa=37811,ma=37812,ga=37813,va=37814,xa=37815,_a=37816,ya=37817,Ma=37818,ba=37819,wa=37820,Sa=37821,Ar=36492,Ta=36494,Ea=36495,Th=36283,Aa=36284,Ca=36285,Pa=36286,Ku=3200,Zu=3201,Eh=0,Ju=1,$n="",Ft="srgb",Hn="srgb-linear",Ja="display-p3",Yr="display-p3-linear",Ir="linear",ut="srgb",Lr="rec709",Nr="p3",Ei=7680,Al=519,$u=512,Qu=513,ed=514,Ah=515,td=516,nd=517,id=518,sd=519,Cl=35044,rd=35048,Pl="300 es",zn=2e3,Ur=2001;class _i{addEventListener(e,t){this._listeners===void 0&&(this._listeners={});const n=this._listeners;n[e]===void 0&&(n[e]=[]),n[e].indexOf(t)===-1&&n[e].push(t)}hasEventListener(e,t){if(this._listeners===void 0)return!1;const n=this._listeners;return n[e]!==void 0&&n[e].indexOf(t)!==-1}removeEventListener(e,t){if(this._listeners===void 0)return;const i=this._listeners[e];if(i!==void 0){const r=i.indexOf(t);r!==-1&&i.splice(r,1)}}dispatchEvent(e){if(this._listeners===void 0)return;const n=this._listeners[e.type];if(n!==void 0){e.target=this;const i=n.slice(0);for(let r=0,o=i.length;r<o;r++)i[r].call(this,e);e.target=null}}}const Bt=["00","01","02","03","04","05","06","07","08","09","0a","0b","0c","0d","0e","0f","10","11","12","13","14","15","16","17","18","19","1a","1b","1c","1d","1e","1f","20","21","22","23","24","25","26","27","28","29","2a","2b","2c","2d","2e","2f","30","31","32","33","34","35","36","37","38","39","3a","3b","3c","3d","3e","3f","40","41","42","43","44","45","46","47","48","49","4a","4b","4c","4d","4e","4f","50","51","52","53","54","55","56","57","58","59","5a","5b","5c","5d","5e","5f","60","61","62","63","64","65","66","67","68","69","6a","6b","6c","6d","6e","6f","70","71","72","73","74","75","76","77","78","79","7a","7b","7c","7d","7e","7f","80","81","82","83","84","85","86","87","88","89","8a","8b","8c","8d","8e","8f","90","91","92","93","94","95","96","97","98","99","9a","9b","9c","9d","9e","9f","a0","a1","a2","a3","a4","a5","a6","a7","a8","a9","aa","ab","ac","ad","ae","af","b0","b1","b2","b3","b4","b5","b6","b7","b8","b9","ba","bb","bc","bd","be","bf","c0","c1","c2","c3","c4","c5","c6","c7","c8","c9","ca","cb","cc","cd","ce","cf","d0","d1","d2","d3","d4","d5","d6","d7","d8","d9","da","db","dc","dd","de","df","e0","e1","e2","e3","e4","e5","e6","e7","e8","e9","ea","eb","ec","ed","ee","ef","f0","f1","f2","f3","f4","f5","f6","f7","f8","f9","fa","fb","fc","fd","fe","ff"];let Rl=1234567;const Ss=Math.PI/180,ns=180/Math.PI;function yi(){const s=Math.random()*4294967295|0,e=Math.random()*4294967295|0,t=Math.random()*4294967295|0,n=Math.random()*4294967295|0;return(Bt[s&255]+Bt[s>>8&255]+Bt[s>>16&255]+Bt[s>>24&255]+"-"+Bt[e&255]+Bt[e>>8&255]+"-"+Bt[e>>16&15|64]+Bt[e>>24&255]+"-"+Bt[t&63|128]+Bt[t>>8&255]+"-"+Bt[t>>16&255]+Bt[t>>24&255]+Bt[n&255]+Bt[n>>8&255]+Bt[n>>16&255]+Bt[n>>24&255]).toLowerCase()}function Tt(s,e,t){return Math.max(e,Math.min(t,s))}function $a(s,e){return(s%e+e)%e}function od(s,e,t,n,i){return n+(s-e)*(i-n)/(t-e)}function ad(s,e,t){return s!==e?(t-s)/(e-s):0}function Ts(s,e,t){return(1-t)*s+t*e}function ld(s,e,t,n){return Ts(s,e,1-Math.exp(-t*n))}function cd(s,e=1){return e-Math.abs($a(s,e*2)-e)}function hd(s,e,t){return s<=e?0:s>=t?1:(s=(s-e)/(t-e),s*s*(3-2*s))}function ud(s,e,t){return s<=e?0:s>=t?1:(s=(s-e)/(t-e),s*s*s*(s*(s*6-15)+10))}function dd(s,e){return s+Math.floor(Math.random()*(e-s+1))}function fd(s,e){return s+Math.random()*(e-s)}function pd(s){return s*(.5-Math.random())}function md(s){s!==void 0&&(Rl=s);let e=Rl+=1831565813;return e=Math.imul(e^e>>>15,e|1),e^=e+Math.imul(e^e>>>7,e|61),((e^e>>>14)>>>0)/4294967296}function gd(s){return s*Ss}function vd(s){return s*ns}function xd(s){return(s&s-1)===0&&s!==0}function _d(s){return Math.pow(2,Math.ceil(Math.log(s)/Math.LN2))}function yd(s){return Math.pow(2,Math.floor(Math.log(s)/Math.LN2))}function Md(s,e,t,n,i){const r=Math.cos,o=Math.sin,a=r(t/2),l=o(t/2),c=r((e+n)/2),h=o((e+n)/2),u=r((e-n)/2),d=o((e-n)/2),f=r((n-e)/2),g=o((n-e)/2);switch(i){case"XYX":s.set(a*h,l*u,l*d,a*c);break;case"YZY":s.set(l*d,a*h,l*u,a*c);break;case"ZXZ":s.set(l*u,l*d,a*h,a*c);break;case"XZX":s.set(a*h,l*g,l*f,a*c);break;case"YXY":s.set(l*f,a*h,l*g,a*c);break;case"ZYZ":s.set(l*g,l*f,a*h,a*c);break;default:console.warn("THREE.MathUtils: .setQuaternionFromProperEuler() encountered an unknown order: "+i)}}function Gi(s,e){switch(e.constructor){case Float32Array:return s;case Uint32Array:return s/4294967295;case Uint16Array:return s/65535;case Uint8Array:return s/255;case Int32Array:return Math.max(s/2147483647,-1);case Int16Array:return Math.max(s/32767,-1);case Int8Array:return Math.max(s/127,-1);default:throw new Error("Invalid component type.")}}function Wt(s,e){switch(e.constructor){case Float32Array:return s;case Uint32Array:return Math.round(s*4294967295);case Uint16Array:return Math.round(s*65535);case Uint8Array:return Math.round(s*255);case Int32Array:return Math.round(s*2147483647);case Int16Array:return Math.round(s*32767);case Int8Array:return Math.round(s*127);default:throw new Error("Invalid component type.")}}const _t={DEG2RAD:Ss,RAD2DEG:ns,generateUUID:yi,clamp:Tt,euclideanModulo:$a,mapLinear:od,inverseLerp:ad,lerp:Ts,damp:ld,pingpong:cd,smoothstep:hd,smootherstep:ud,randInt:dd,randFloat:fd,randFloatSpread:pd,seededRandom:md,degToRad:gd,radToDeg:vd,isPowerOfTwo:xd,ceilPowerOfTwo:_d,floorPowerOfTwo:yd,setQuaternionFromProperEuler:Md,normalize:Wt,denormalize:Gi};class Q{constructor(e=0,t=0){Q.prototype.isVector2=!0,this.x=e,this.y=t}get width(){return this.x}set width(e){this.x=e}get height(){return this.y}set height(e){this.y=e}set(e,t){return this.x=e,this.y=t,this}setScalar(e){return this.x=e,this.y=e,this}setX(e){return this.x=e,this}setY(e){return this.y=e,this}setComponent(e,t){switch(e){case 0:this.x=t;break;case 1:this.y=t;break;default:throw new Error("index is out of range: "+e)}return this}getComponent(e){switch(e){case 0:return this.x;case 1:return this.y;default:throw new Error("index is out of range: "+e)}}clone(){return new this.constructor(this.x,this.y)}copy(e){return this.x=e.x,this.y=e.y,this}add(e){return this.x+=e.x,this.y+=e.y,this}addScalar(e){return this.x+=e,this.y+=e,this}addVectors(e,t){return this.x=e.x+t.x,this.y=e.y+t.y,this}addScaledVector(e,t){return this.x+=e.x*t,this.y+=e.y*t,this}sub(e){return this.x-=e.x,this.y-=e.y,this}subScalar(e){return this.x-=e,this.y-=e,this}subVectors(e,t){return this.x=e.x-t.x,this.y=e.y-t.y,this}multiply(e){return this.x*=e.x,this.y*=e.y,this}multiplyScalar(e){return this.x*=e,this.y*=e,this}divide(e){return this.x/=e.x,this.y/=e.y,this}divideScalar(e){return this.multiplyScalar(1/e)}applyMatrix3(e){const t=this.x,n=this.y,i=e.elements;return this.x=i[0]*t+i[3]*n+i[6],this.y=i[1]*t+i[4]*n+i[7],this}min(e){return this.x=Math.min(this.x,e.x),this.y=Math.min(this.y,e.y),this}max(e){return this.x=Math.max(this.x,e.x),this.y=Math.max(this.y,e.y),this}clamp(e,t){return this.x=Math.max(e.x,Math.min(t.x,this.x)),this.y=Math.max(e.y,Math.min(t.y,this.y)),this}clampScalar(e,t){return this.x=Math.max(e,Math.min(t,this.x)),this.y=Math.max(e,Math.min(t,this.y)),this}clampLength(e,t){const n=this.length();return this.divideScalar(n||1).multiplyScalar(Math.max(e,Math.min(t,n)))}floor(){return this.x=Math.floor(this.x),this.y=Math.floor(this.y),this}ceil(){return this.x=Math.ceil(this.x),this.y=Math.ceil(this.y),this}round(){return this.x=Math.round(this.x),this.y=Math.round(this.y),this}roundToZero(){return this.x=Math.trunc(this.x),this.y=Math.trunc(this.y),this}negate(){return this.x=-this.x,this.y=-this.y,this}dot(e){return this.x*e.x+this.y*e.y}cross(e){return this.x*e.y-this.y*e.x}lengthSq(){return this.x*this.x+this.y*this.y}length(){return Math.sqrt(this.x*this.x+this.y*this.y)}manhattanLength(){return Math.abs(this.x)+Math.abs(this.y)}normalize(){return this.divideScalar(this.length()||1)}angle(){return Math.atan2(-this.y,-this.x)+Math.PI}angleTo(e){const t=Math.sqrt(this.lengthSq()*e.lengthSq());if(t===0)return Math.PI/2;const n=this.dot(e)/t;return Math.acos(Tt(n,-1,1))}distanceTo(e){return Math.sqrt(this.distanceToSquared(e))}distanceToSquared(e){const t=this.x-e.x,n=this.y-e.y;return t*t+n*n}manhattanDistanceTo(e){return Math.abs(this.x-e.x)+Math.abs(this.y-e.y)}setLength(e){return this.normalize().multiplyScalar(e)}lerp(e,t){return this.x+=(e.x-this.x)*t,this.y+=(e.y-this.y)*t,this}lerpVectors(e,t,n){return this.x=e.x+(t.x-e.x)*n,this.y=e.y+(t.y-e.y)*n,this}equals(e){return e.x===this.x&&e.y===this.y}fromArray(e,t=0){return this.x=e[t],this.y=e[t+1],this}toArray(e=[],t=0){return e[t]=this.x,e[t+1]=this.y,e}fromBufferAttribute(e,t){return this.x=e.getX(t),this.y=e.getY(t),this}rotateAround(e,t){const n=Math.cos(t),i=Math.sin(t),r=this.x-e.x,o=this.y-e.y;return this.x=r*n-o*i+e.x,this.y=r*i+o*n+e.y,this}random(){return this.x=Math.random(),this.y=Math.random(),this}*[Symbol.iterator](){yield this.x,yield this.y}}class Ye{constructor(e,t,n,i,r,o,a,l,c){Ye.prototype.isMatrix3=!0,this.elements=[1,0,0,0,1,0,0,0,1],e!==void 0&&this.set(e,t,n,i,r,o,a,l,c)}set(e,t,n,i,r,o,a,l,c){const h=this.elements;return h[0]=e,h[1]=i,h[2]=a,h[3]=t,h[4]=r,h[5]=l,h[6]=n,h[7]=o,h[8]=c,this}identity(){return this.set(1,0,0,0,1,0,0,0,1),this}copy(e){const t=this.elements,n=e.elements;return t[0]=n[0],t[1]=n[1],t[2]=n[2],t[3]=n[3],t[4]=n[4],t[5]=n[5],t[6]=n[6],t[7]=n[7],t[8]=n[8],this}extractBasis(e,t,n){return e.setFromMatrix3Column(this,0),t.setFromMatrix3Column(this,1),n.setFromMatrix3Column(this,2),this}setFromMatrix4(e){const t=e.elements;return this.set(t[0],t[4],t[8],t[1],t[5],t[9],t[2],t[6],t[10]),this}multiply(e){return this.multiplyMatrices(this,e)}premultiply(e){return this.multiplyMatrices(e,this)}multiplyMatrices(e,t){const n=e.elements,i=t.elements,r=this.elements,o=n[0],a=n[3],l=n[6],c=n[1],h=n[4],u=n[7],d=n[2],f=n[5],g=n[8],x=i[0],p=i[3],m=i[6],_=i[1],v=i[4],M=i[7],S=i[2],E=i[5],C=i[8];return r[0]=o*x+a*_+l*S,r[3]=o*p+a*v+l*E,r[6]=o*m+a*M+l*C,r[1]=c*x+h*_+u*S,r[4]=c*p+h*v+u*E,r[7]=c*m+h*M+u*C,r[2]=d*x+f*_+g*S,r[5]=d*p+f*v+g*E,r[8]=d*m+f*M+g*C,this}multiplyScalar(e){const t=this.elements;return t[0]*=e,t[3]*=e,t[6]*=e,t[1]*=e,t[4]*=e,t[7]*=e,t[2]*=e,t[5]*=e,t[8]*=e,this}determinant(){const e=this.elements,t=e[0],n=e[1],i=e[2],r=e[3],o=e[4],a=e[5],l=e[6],c=e[7],h=e[8];return t*o*h-t*a*c-n*r*h+n*a*l+i*r*c-i*o*l}invert(){const e=this.elements,t=e[0],n=e[1],i=e[2],r=e[3],o=e[4],a=e[5],l=e[6],c=e[7],h=e[8],u=h*o-a*c,d=a*l-h*r,f=c*r-o*l,g=t*u+n*d+i*f;if(g===0)return this.set(0,0,0,0,0,0,0,0,0);const x=1/g;return e[0]=u*x,e[1]=(i*c-h*n)*x,e[2]=(a*n-i*o)*x,e[3]=d*x,e[4]=(h*t-i*l)*x,e[5]=(i*r-a*t)*x,e[6]=f*x,e[7]=(n*l-c*t)*x,e[8]=(o*t-n*r)*x,this}transpose(){let e;const t=this.elements;return e=t[1],t[1]=t[3],t[3]=e,e=t[2],t[2]=t[6],t[6]=e,e=t[5],t[5]=t[7],t[7]=e,this}getNormalMatrix(e){return this.setFromMatrix4(e).invert().transpose()}transposeIntoArray(e){const t=this.elements;return e[0]=t[0],e[1]=t[3],e[2]=t[6],e[3]=t[1],e[4]=t[4],e[5]=t[7],e[6]=t[2],e[7]=t[5],e[8]=t[8],this}setUvTransform(e,t,n,i,r,o,a){const l=Math.cos(r),c=Math.sin(r);return this.set(n*l,n*c,-n*(l*o+c*a)+o+e,-i*c,i*l,-i*(-c*o+l*a)+a+t,0,0,1),this}scale(e,t){return this.premultiply(ro.makeScale(e,t)),this}rotate(e){return this.premultiply(ro.makeRotation(-e)),this}translate(e,t){return this.premultiply(ro.makeTranslation(e,t)),this}makeTranslation(e,t){return e.isVector2?this.set(1,0,e.x,0,1,e.y,0,0,1):this.set(1,0,e,0,1,t,0,0,1),this}makeRotation(e){const t=Math.cos(e),n=Math.sin(e);return this.set(t,-n,0,n,t,0,0,0,1),this}makeScale(e,t){return this.set(e,0,0,0,t,0,0,0,1),this}equals(e){const t=this.elements,n=e.elements;for(let i=0;i<9;i++)if(t[i]!==n[i])return!1;return!0}fromArray(e,t=0){for(let n=0;n<9;n++)this.elements[n]=e[n+t];return this}toArray(e=[],t=0){const n=this.elements;return e[t]=n[0],e[t+1]=n[1],e[t+2]=n[2],e[t+3]=n[3],e[t+4]=n[4],e[t+5]=n[5],e[t+6]=n[6],e[t+7]=n[7],e[t+8]=n[8],e}clone(){return new this.constructor().fromArray(this.elements)}}const ro=new Ye;function Ch(s){for(let e=s.length-1;e>=0;--e)if(s[e]>=65535)return!0;return!1}function Or(s){return document.createElementNS("http://www.w3.org/1999/xhtml",s)}function bd(){const s=Or("canvas");return s.style.display="block",s}const Dl={};function Cr(s){s in Dl||(Dl[s]=!0,console.warn(s))}function wd(s,e,t){return new Promise(function(n,i){function r(){switch(s.clientWaitSync(e,s.SYNC_FLUSH_COMMANDS_BIT,0)){case s.WAIT_FAILED:i();break;case s.TIMEOUT_EXPIRED:setTimeout(r,t);break;default:n()}}setTimeout(r,t)})}function Sd(s){const e=s.elements;e[2]=.5*e[2]+.5*e[3],e[6]=.5*e[6]+.5*e[7],e[10]=.5*e[10]+.5*e[11],e[14]=.5*e[14]+.5*e[15]}function Td(s){const e=s.elements;e[11]===-1?(e[10]=-e[10]-1,e[14]=-e[14]):(e[10]=-e[10],e[14]=-e[14]+1)}const Il=new Ye().set(.8224621,.177538,0,.0331941,.9668058,0,.0170827,.0723974,.9105199),Ll=new Ye().set(1.2249401,-.2249404,0,-.0420569,1.0420571,0,-.0196376,-.0786361,1.0982735),us={[Hn]:{transfer:Ir,primaries:Lr,luminanceCoefficients:[.2126,.7152,.0722],toReference:s=>s,fromReference:s=>s},[Ft]:{transfer:ut,primaries:Lr,luminanceCoefficients:[.2126,.7152,.0722],toReference:s=>s.convertSRGBToLinear(),fromReference:s=>s.convertLinearToSRGB()},[Yr]:{transfer:Ir,primaries:Nr,luminanceCoefficients:[.2289,.6917,.0793],toReference:s=>s.applyMatrix3(Ll),fromReference:s=>s.applyMatrix3(Il)},[Ja]:{transfer:ut,primaries:Nr,luminanceCoefficients:[.2289,.6917,.0793],toReference:s=>s.convertSRGBToLinear().applyMatrix3(Ll),fromReference:s=>s.applyMatrix3(Il).convertLinearToSRGB()}},Ed=new Set([Hn,Yr]),nt={enabled:!0,_workingColorSpace:Hn,get workingColorSpace(){return this._workingColorSpace},set workingColorSpace(s){if(!Ed.has(s))throw new Error(`Unsupported working color space, "${s}".`);this._workingColorSpace=s},convert:function(s,e,t){if(this.enabled===!1||e===t||!e||!t)return s;const n=us[e].toReference,i=us[t].fromReference;return i(n(s))},fromWorkingColorSpace:function(s,e){return this.convert(s,this._workingColorSpace,e)},toWorkingColorSpace:function(s,e){return this.convert(s,e,this._workingColorSpace)},getPrimaries:function(s){return us[s].primaries},getTransfer:function(s){return s===$n?Ir:us[s].transfer},getLuminanceCoefficients:function(s,e=this._workingColorSpace){return s.fromArray(us[e].luminanceCoefficients)}};function Ki(s){return s<.04045?s*.0773993808:Math.pow(s*.9478672986+.0521327014,2.4)}function oo(s){return s<.0031308?s*12.92:1.055*Math.pow(s,.41666)-.055}let Ai;class Ad{static getDataURL(e){if(/^data:/i.test(e.src)||typeof HTMLCanvasElement>"u")return e.src;let t;if(e instanceof HTMLCanvasElement)t=e;else{Ai===void 0&&(Ai=Or("canvas")),Ai.width=e.width,Ai.height=e.height;const n=Ai.getContext("2d");e instanceof ImageData?n.putImageData(e,0,0):n.drawImage(e,0,0,e.width,e.height),t=Ai}return t.width>2048||t.height>2048?(console.warn("THREE.ImageUtils.getDataURL: Image converted to jpg for performance reasons",e),t.toDataURL("image/jpeg",.6)):t.toDataURL("image/png")}static sRGBToLinear(e){if(typeof HTMLImageElement<"u"&&e instanceof HTMLImageElement||typeof HTMLCanvasElement<"u"&&e instanceof HTMLCanvasElement||typeof ImageBitmap<"u"&&e instanceof ImageBitmap){const t=Or("canvas");t.width=e.width,t.height=e.height;const n=t.getContext("2d");n.drawImage(e,0,0,e.width,e.height);const i=n.getImageData(0,0,e.width,e.height),r=i.data;for(let o=0;o<r.length;o++)r[o]=Ki(r[o]/255)*255;return n.putImageData(i,0,0),t}else if(e.data){const t=e.data.slice(0);for(let n=0;n<t.length;n++)t instanceof Uint8Array||t instanceof Uint8ClampedArray?t[n]=Math.floor(Ki(t[n]/255)*255):t[n]=Ki(t[n]);return{data:t,width:e.width,height:e.height}}else return console.warn("THREE.ImageUtils.sRGBToLinear(): Unsupported image type. No color space conversion applied."),e}}let Cd=0;class Ph{constructor(e=null){this.isSource=!0,Object.defineProperty(this,"id",{value:Cd++}),this.uuid=yi(),this.data=e,this.dataReady=!0,this.version=0}set needsUpdate(e){e===!0&&this.version++}toJSON(e){const t=e===void 0||typeof e=="string";if(!t&&e.images[this.uuid]!==void 0)return e.images[this.uuid];const n={uuid:this.uuid,url:""},i=this.data;if(i!==null){let r;if(Array.isArray(i)){r=[];for(let o=0,a=i.length;o<a;o++)i[o].isDataTexture?r.push(ao(i[o].image)):r.push(ao(i[o]))}else r=ao(i);n.url=r}return t||(e.images[this.uuid]=n),n}}function ao(s){return typeof HTMLImageElement<"u"&&s instanceof HTMLImageElement||typeof HTMLCanvasElement<"u"&&s instanceof HTMLCanvasElement||typeof ImageBitmap<"u"&&s instanceof ImageBitmap?Ad.getDataURL(s):s.data?{data:Array.from(s.data),width:s.width,height:s.height,type:s.data.constructor.name}:(console.warn("THREE.Texture: Unable to serialize Texture."),{})}let Pd=0;class It extends _i{constructor(e=It.DEFAULT_IMAGE,t=It.DEFAULT_MAPPING,n=fi,i=fi,r=Ct,o=pi,a=sn,l=Vn,c=It.DEFAULT_ANISOTROPY,h=$n){super(),this.isTexture=!0,Object.defineProperty(this,"id",{value:Pd++}),this.uuid=yi(),this.name="",this.source=new Ph(e),this.mipmaps=[],this.mapping=t,this.channel=0,this.wrapS=n,this.wrapT=i,this.magFilter=r,this.minFilter=o,this.anisotropy=c,this.format=a,this.internalFormat=null,this.type=l,this.offset=new Q(0,0),this.repeat=new Q(1,1),this.center=new Q(0,0),this.rotation=0,this.matrixAutoUpdate=!0,this.matrix=new Ye,this.generateMipmaps=!0,this.premultiplyAlpha=!1,this.flipY=!0,this.unpackAlignment=4,this.colorSpace=h,this.userData={},this.version=0,this.onUpdate=null,this.isRenderTargetTexture=!1,this.pmremVersion=0}get image(){return this.source.data}set image(e=null){this.source.data=e}updateMatrix(){this.matrix.setUvTransform(this.offset.x,this.offset.y,this.repeat.x,this.repeat.y,this.rotation,this.center.x,this.center.y)}clone(){return new this.constructor().copy(this)}copy(e){return this.name=e.name,this.source=e.source,this.mipmaps=e.mipmaps.slice(0),this.mapping=e.mapping,this.channel=e.channel,this.wrapS=e.wrapS,this.wrapT=e.wrapT,this.magFilter=e.magFilter,this.minFilter=e.minFilter,this.anisotropy=e.anisotropy,this.format=e.format,this.internalFormat=e.internalFormat,this.type=e.type,this.offset.copy(e.offset),this.repeat.copy(e.repeat),this.center.copy(e.center),this.rotation=e.rotation,this.matrixAutoUpdate=e.matrixAutoUpdate,this.matrix.copy(e.matrix),this.generateMipmaps=e.generateMipmaps,this.premultiplyAlpha=e.premultiplyAlpha,this.flipY=e.flipY,this.unpackAlignment=e.unpackAlignment,this.colorSpace=e.colorSpace,this.userData=JSON.parse(JSON.stringify(e.userData)),this.needsUpdate=!0,this}toJSON(e){const t=e===void 0||typeof e=="string";if(!t&&e.textures[this.uuid]!==void 0)return e.textures[this.uuid];const n={metadata:{version:4.6,type:"Texture",generator:"Texture.toJSON"},uuid:this.uuid,name:this.name,image:this.source.toJSON(e).uuid,mapping:this.mapping,channel:this.channel,repeat:[this.repeat.x,this.repeat.y],offset:[this.offset.x,this.offset.y],center:[this.center.x,this.center.y],rotation:this.rotation,wrap:[this.wrapS,this.wrapT],format:this.format,internalFormat:this.internalFormat,type:this.type,colorSpace:this.colorSpace,minFilter:this.minFilter,magFilter:this.magFilter,anisotropy:this.anisotropy,flipY:this.flipY,generateMipmaps:this.generateMipmaps,premultiplyAlpha:this.premultiplyAlpha,unpackAlignment:this.unpackAlignment};return Object.keys(this.userData).length>0&&(n.userData=this.userData),t||(e.textures[this.uuid]=n),n}dispose(){this.dispatchEvent({type:"dispose"})}transformUv(e){if(this.mapping!==gh)return e;if(e.applyMatrix3(this.matrix),e.x<0||e.x>1)switch(this.wrapS){case na:e.x=e.x-Math.floor(e.x);break;case fi:e.x=e.x<0?0:1;break;case ia:Math.abs(Math.floor(e.x)%2)===1?e.x=Math.ceil(e.x)-e.x:e.x=e.x-Math.floor(e.x);break}if(e.y<0||e.y>1)switch(this.wrapT){case na:e.y=e.y-Math.floor(e.y);break;case fi:e.y=e.y<0?0:1;break;case ia:Math.abs(Math.floor(e.y)%2)===1?e.y=Math.ceil(e.y)-e.y:e.y=e.y-Math.floor(e.y);break}return this.flipY&&(e.y=1-e.y),e}set needsUpdate(e){e===!0&&(this.version++,this.source.needsUpdate=!0)}set needsPMREMUpdate(e){e===!0&&this.pmremVersion++}}It.DEFAULT_IMAGE=null;It.DEFAULT_MAPPING=gh;It.DEFAULT_ANISOTROPY=1;class ot{constructor(e=0,t=0,n=0,i=1){ot.prototype.isVector4=!0,this.x=e,this.y=t,this.z=n,this.w=i}get width(){return this.z}set width(e){this.z=e}get height(){return this.w}set height(e){this.w=e}set(e,t,n,i){return this.x=e,this.y=t,this.z=n,this.w=i,this}setScalar(e){return this.x=e,this.y=e,this.z=e,this.w=e,this}setX(e){return this.x=e,this}setY(e){return this.y=e,this}setZ(e){return this.z=e,this}setW(e){return this.w=e,this}setComponent(e,t){switch(e){case 0:this.x=t;break;case 1:this.y=t;break;case 2:this.z=t;break;case 3:this.w=t;break;default:throw new Error("index is out of range: "+e)}return this}getComponent(e){switch(e){case 0:return this.x;case 1:return this.y;case 2:return this.z;case 3:return this.w;default:throw new Error("index is out of range: "+e)}}clone(){return new this.constructor(this.x,this.y,this.z,this.w)}copy(e){return this.x=e.x,this.y=e.y,this.z=e.z,this.w=e.w!==void 0?e.w:1,this}add(e){return this.x+=e.x,this.y+=e.y,this.z+=e.z,this.w+=e.w,this}addScalar(e){return this.x+=e,this.y+=e,this.z+=e,this.w+=e,this}addVectors(e,t){return this.x=e.x+t.x,this.y=e.y+t.y,this.z=e.z+t.z,this.w=e.w+t.w,this}addScaledVector(e,t){return this.x+=e.x*t,this.y+=e.y*t,this.z+=e.z*t,this.w+=e.w*t,this}sub(e){return this.x-=e.x,this.y-=e.y,this.z-=e.z,this.w-=e.w,this}subScalar(e){return this.x-=e,this.y-=e,this.z-=e,this.w-=e,this}subVectors(e,t){return this.x=e.x-t.x,this.y=e.y-t.y,this.z=e.z-t.z,this.w=e.w-t.w,this}multiply(e){return this.x*=e.x,this.y*=e.y,this.z*=e.z,this.w*=e.w,this}multiplyScalar(e){return this.x*=e,this.y*=e,this.z*=e,this.w*=e,this}applyMatrix4(e){const t=this.x,n=this.y,i=this.z,r=this.w,o=e.elements;return this.x=o[0]*t+o[4]*n+o[8]*i+o[12]*r,this.y=o[1]*t+o[5]*n+o[9]*i+o[13]*r,this.z=o[2]*t+o[6]*n+o[10]*i+o[14]*r,this.w=o[3]*t+o[7]*n+o[11]*i+o[15]*r,this}divideScalar(e){return this.multiplyScalar(1/e)}setAxisAngleFromQuaternion(e){this.w=2*Math.acos(e.w);const t=Math.sqrt(1-e.w*e.w);return t<1e-4?(this.x=1,this.y=0,this.z=0):(this.x=e.x/t,this.y=e.y/t,this.z=e.z/t),this}setAxisAngleFromRotationMatrix(e){let t,n,i,r;const l=e.elements,c=l[0],h=l[4],u=l[8],d=l[1],f=l[5],g=l[9],x=l[2],p=l[6],m=l[10];if(Math.abs(h-d)<.01&&Math.abs(u-x)<.01&&Math.abs(g-p)<.01){if(Math.abs(h+d)<.1&&Math.abs(u+x)<.1&&Math.abs(g+p)<.1&&Math.abs(c+f+m-3)<.1)return this.set(1,0,0,0),this;t=Math.PI;const v=(c+1)/2,M=(f+1)/2,S=(m+1)/2,E=(h+d)/4,C=(u+x)/4,z=(g+p)/4;return v>M&&v>S?v<.01?(n=0,i=.707106781,r=.707106781):(n=Math.sqrt(v),i=E/n,r=C/n):M>S?M<.01?(n=.707106781,i=0,r=.707106781):(i=Math.sqrt(M),n=E/i,r=z/i):S<.01?(n=.707106781,i=.707106781,r=0):(r=Math.sqrt(S),n=C/r,i=z/r),this.set(n,i,r,t),this}let _=Math.sqrt((p-g)*(p-g)+(u-x)*(u-x)+(d-h)*(d-h));return Math.abs(_)<.001&&(_=1),this.x=(p-g)/_,this.y=(u-x)/_,this.z=(d-h)/_,this.w=Math.acos((c+f+m-1)/2),this}setFromMatrixPosition(e){const t=e.elements;return this.x=t[12],this.y=t[13],this.z=t[14],this.w=t[15],this}min(e){return this.x=Math.min(this.x,e.x),this.y=Math.min(this.y,e.y),this.z=Math.min(this.z,e.z),this.w=Math.min(this.w,e.w),this}max(e){return this.x=Math.max(this.x,e.x),this.y=Math.max(this.y,e.y),this.z=Math.max(this.z,e.z),this.w=Math.max(this.w,e.w),this}clamp(e,t){return this.x=Math.max(e.x,Math.min(t.x,this.x)),this.y=Math.max(e.y,Math.min(t.y,this.y)),this.z=Math.max(e.z,Math.min(t.z,this.z)),this.w=Math.max(e.w,Math.min(t.w,this.w)),this}clampScalar(e,t){return this.x=Math.max(e,Math.min(t,this.x)),this.y=Math.max(e,Math.min(t,this.y)),this.z=Math.max(e,Math.min(t,this.z)),this.w=Math.max(e,Math.min(t,this.w)),this}clampLength(e,t){const n=this.length();return this.divideScalar(n||1).multiplyScalar(Math.max(e,Math.min(t,n)))}floor(){return this.x=Math.floor(this.x),this.y=Math.floor(this.y),this.z=Math.floor(this.z),this.w=Math.floor(this.w),this}ceil(){return this.x=Math.ceil(this.x),this.y=Math.ceil(this.y),this.z=Math.ceil(this.z),this.w=Math.ceil(this.w),this}round(){return this.x=Math.round(this.x),this.y=Math.round(this.y),this.z=Math.round(this.z),this.w=Math.round(this.w),this}roundToZero(){return this.x=Math.trunc(this.x),this.y=Math.trunc(this.y),this.z=Math.trunc(this.z),this.w=Math.trunc(this.w),this}negate(){return this.x=-this.x,this.y=-this.y,this.z=-this.z,this.w=-this.w,this}dot(e){return this.x*e.x+this.y*e.y+this.z*e.z+this.w*e.w}lengthSq(){return this.x*this.x+this.y*this.y+this.z*this.z+this.w*this.w}length(){return Math.sqrt(this.x*this.x+this.y*this.y+this.z*this.z+this.w*this.w)}manhattanLength(){return Math.abs(this.x)+Math.abs(this.y)+Math.abs(this.z)+Math.abs(this.w)}normalize(){return this.divideScalar(this.length()||1)}setLength(e){return this.normalize().multiplyScalar(e)}lerp(e,t){return this.x+=(e.x-this.x)*t,this.y+=(e.y-this.y)*t,this.z+=(e.z-this.z)*t,this.w+=(e.w-this.w)*t,this}lerpVectors(e,t,n){return this.x=e.x+(t.x-e.x)*n,this.y=e.y+(t.y-e.y)*n,this.z=e.z+(t.z-e.z)*n,this.w=e.w+(t.w-e.w)*n,this}equals(e){return e.x===this.x&&e.y===this.y&&e.z===this.z&&e.w===this.w}fromArray(e,t=0){return this.x=e[t],this.y=e[t+1],this.z=e[t+2],this.w=e[t+3],this}toArray(e=[],t=0){return e[t]=this.x,e[t+1]=this.y,e[t+2]=this.z,e[t+3]=this.w,e}fromBufferAttribute(e,t){return this.x=e.getX(t),this.y=e.getY(t),this.z=e.getZ(t),this.w=e.getW(t),this}random(){return this.x=Math.random(),this.y=Math.random(),this.z=Math.random(),this.w=Math.random(),this}*[Symbol.iterator](){yield this.x,yield this.y,yield this.z,yield this.w}}class Rd extends _i{constructor(e=1,t=1,n={}){super(),this.isRenderTarget=!0,this.width=e,this.height=t,this.depth=1,this.scissor=new ot(0,0,e,t),this.scissorTest=!1,this.viewport=new ot(0,0,e,t);const i={width:e,height:t,depth:1};n=Object.assign({generateMipmaps:!1,internalFormat:null,minFilter:Ct,depthBuffer:!0,stencilBuffer:!1,resolveDepthBuffer:!0,resolveStencilBuffer:!0,depthTexture:null,samples:0,count:1},n);const r=new It(i,n.mapping,n.wrapS,n.wrapT,n.magFilter,n.minFilter,n.format,n.type,n.anisotropy,n.colorSpace);r.flipY=!1,r.generateMipmaps=n.generateMipmaps,r.internalFormat=n.internalFormat,this.textures=[];const o=n.count;for(let a=0;a<o;a++)this.textures[a]=r.clone(),this.textures[a].isRenderTargetTexture=!0;this.depthBuffer=n.depthBuffer,this.stencilBuffer=n.stencilBuffer,this.resolveDepthBuffer=n.resolveDepthBuffer,this.resolveStencilBuffer=n.resolveStencilBuffer,this.depthTexture=n.depthTexture,this.samples=n.samples}get texture(){return this.textures[0]}set texture(e){this.textures[0]=e}setSize(e,t,n=1){if(this.width!==e||this.height!==t||this.depth!==n){this.width=e,this.height=t,this.depth=n;for(let i=0,r=this.textures.length;i<r;i++)this.textures[i].image.width=e,this.textures[i].image.height=t,this.textures[i].image.depth=n;this.dispose()}this.viewport.set(0,0,e,t),this.scissor.set(0,0,e,t)}clone(){return new this.constructor().copy(this)}copy(e){this.width=e.width,this.height=e.height,this.depth=e.depth,this.scissor.copy(e.scissor),this.scissorTest=e.scissorTest,this.viewport.copy(e.viewport),this.textures.length=0;for(let n=0,i=e.textures.length;n<i;n++)this.textures[n]=e.textures[n].clone(),this.textures[n].isRenderTargetTexture=!0;const t=Object.assign({},e.texture.image);return this.texture.source=new Ph(t),this.depthBuffer=e.depthBuffer,this.stencilBuffer=e.stencilBuffer,this.resolveDepthBuffer=e.resolveDepthBuffer,this.resolveStencilBuffer=e.resolveStencilBuffer,e.depthTexture!==null&&(this.depthTexture=e.depthTexture.clone()),this.samples=e.samples,this}dispose(){this.dispatchEvent({type:"dispose"})}}class un extends Rd{constructor(e=1,t=1,n={}){super(e,t,n),this.isWebGLRenderTarget=!0}}class Rh extends It{constructor(e=null,t=1,n=1,i=1){super(null),this.isDataArrayTexture=!0,this.image={data:e,width:t,height:n,depth:i},this.magFilter=$t,this.minFilter=$t,this.wrapR=fi,this.generateMipmaps=!1,this.flipY=!1,this.unpackAlignment=1,this.layerUpdates=new Set}addLayerUpdate(e){this.layerUpdates.add(e)}clearLayerUpdates(){this.layerUpdates.clear()}}class Dd extends It{constructor(e=null,t=1,n=1,i=1){super(null),this.isData3DTexture=!0,this.image={data:e,width:t,height:n,depth:i},this.magFilter=$t,this.minFilter=$t,this.wrapR=fi,this.generateMipmaps=!1,this.flipY=!1,this.unpackAlignment=1}}class Pt{constructor(e=0,t=0,n=0,i=1){this.isQuaternion=!0,this._x=e,this._y=t,this._z=n,this._w=i}static slerpFlat(e,t,n,i,r,o,a){let l=n[i+0],c=n[i+1],h=n[i+2],u=n[i+3];const d=r[o+0],f=r[o+1],g=r[o+2],x=r[o+3];if(a===0){e[t+0]=l,e[t+1]=c,e[t+2]=h,e[t+3]=u;return}if(a===1){e[t+0]=d,e[t+1]=f,e[t+2]=g,e[t+3]=x;return}if(u!==x||l!==d||c!==f||h!==g){let p=1-a;const m=l*d+c*f+h*g+u*x,_=m>=0?1:-1,v=1-m*m;if(v>Number.EPSILON){const S=Math.sqrt(v),E=Math.atan2(S,m*_);p=Math.sin(p*E)/S,a=Math.sin(a*E)/S}const M=a*_;if(l=l*p+d*M,c=c*p+f*M,h=h*p+g*M,u=u*p+x*M,p===1-a){const S=1/Math.sqrt(l*l+c*c+h*h+u*u);l*=S,c*=S,h*=S,u*=S}}e[t]=l,e[t+1]=c,e[t+2]=h,e[t+3]=u}static multiplyQuaternionsFlat(e,t,n,i,r,o){const a=n[i],l=n[i+1],c=n[i+2],h=n[i+3],u=r[o],d=r[o+1],f=r[o+2],g=r[o+3];return e[t]=a*g+h*u+l*f-c*d,e[t+1]=l*g+h*d+c*u-a*f,e[t+2]=c*g+h*f+a*d-l*u,e[t+3]=h*g-a*u-l*d-c*f,e}get x(){return this._x}set x(e){this._x=e,this._onChangeCallback()}get y(){return this._y}set y(e){this._y=e,this._onChangeCallback()}get z(){return this._z}set z(e){this._z=e,this._onChangeCallback()}get w(){return this._w}set w(e){this._w=e,this._onChangeCallback()}set(e,t,n,i){return this._x=e,this._y=t,this._z=n,this._w=i,this._onChangeCallback(),this}clone(){return new this.constructor(this._x,this._y,this._z,this._w)}copy(e){return this._x=e.x,this._y=e.y,this._z=e.z,this._w=e.w,this._onChangeCallback(),this}setFromEuler(e,t=!0){const n=e._x,i=e._y,r=e._z,o=e._order,a=Math.cos,l=Math.sin,c=a(n/2),h=a(i/2),u=a(r/2),d=l(n/2),f=l(i/2),g=l(r/2);switch(o){case"XYZ":this._x=d*h*u+c*f*g,this._y=c*f*u-d*h*g,this._z=c*h*g+d*f*u,this._w=c*h*u-d*f*g;break;case"YXZ":this._x=d*h*u+c*f*g,this._y=c*f*u-d*h*g,this._z=c*h*g-d*f*u,this._w=c*h*u+d*f*g;break;case"ZXY":this._x=d*h*u-c*f*g,this._y=c*f*u+d*h*g,this._z=c*h*g+d*f*u,this._w=c*h*u-d*f*g;break;case"ZYX":this._x=d*h*u-c*f*g,this._y=c*f*u+d*h*g,this._z=c*h*g-d*f*u,this._w=c*h*u+d*f*g;break;case"YZX":this._x=d*h*u+c*f*g,this._y=c*f*u+d*h*g,this._z=c*h*g-d*f*u,this._w=c*h*u-d*f*g;break;case"XZY":this._x=d*h*u-c*f*g,this._y=c*f*u-d*h*g,this._z=c*h*g+d*f*u,this._w=c*h*u+d*f*g;break;default:console.warn("THREE.Quaternion: .setFromEuler() encountered an unknown order: "+o)}return t===!0&&this._onChangeCallback(),this}setFromAxisAngle(e,t){const n=t/2,i=Math.sin(n);return this._x=e.x*i,this._y=e.y*i,this._z=e.z*i,this._w=Math.cos(n),this._onChangeCallback(),this}setFromRotationMatrix(e){const t=e.elements,n=t[0],i=t[4],r=t[8],o=t[1],a=t[5],l=t[9],c=t[2],h=t[6],u=t[10],d=n+a+u;if(d>0){const f=.5/Math.sqrt(d+1);this._w=.25/f,this._x=(h-l)*f,this._y=(r-c)*f,this._z=(o-i)*f}else if(n>a&&n>u){const f=2*Math.sqrt(1+n-a-u);this._w=(h-l)/f,this._x=.25*f,this._y=(i+o)/f,this._z=(r+c)/f}else if(a>u){const f=2*Math.sqrt(1+a-n-u);this._w=(r-c)/f,this._x=(i+o)/f,this._y=.25*f,this._z=(l+h)/f}else{const f=2*Math.sqrt(1+u-n-a);this._w=(o-i)/f,this._x=(r+c)/f,this._y=(l+h)/f,this._z=.25*f}return this._onChangeCallback(),this}setFromUnitVectors(e,t){let n=e.dot(t)+1;return n<Number.EPSILON?(n=0,Math.abs(e.x)>Math.abs(e.z)?(this._x=-e.y,this._y=e.x,this._z=0,this._w=n):(this._x=0,this._y=-e.z,this._z=e.y,this._w=n)):(this._x=e.y*t.z-e.z*t.y,this._y=e.z*t.x-e.x*t.z,this._z=e.x*t.y-e.y*t.x,this._w=n),this.normalize()}angleTo(e){return 2*Math.acos(Math.abs(Tt(this.dot(e),-1,1)))}rotateTowards(e,t){const n=this.angleTo(e);if(n===0)return this;const i=Math.min(1,t/n);return this.slerp(e,i),this}identity(){return this.set(0,0,0,1)}invert(){return this.conjugate()}conjugate(){return this._x*=-1,this._y*=-1,this._z*=-1,this._onChangeCallback(),this}dot(e){return this._x*e._x+this._y*e._y+this._z*e._z+this._w*e._w}lengthSq(){return this._x*this._x+this._y*this._y+this._z*this._z+this._w*this._w}length(){return Math.sqrt(this._x*this._x+this._y*this._y+this._z*this._z+this._w*this._w)}normalize(){let e=this.length();return e===0?(this._x=0,this._y=0,this._z=0,this._w=1):(e=1/e,this._x=this._x*e,this._y=this._y*e,this._z=this._z*e,this._w=this._w*e),this._onChangeCallback(),this}multiply(e){return this.multiplyQuaternions(this,e)}premultiply(e){return this.multiplyQuaternions(e,this)}multiplyQuaternions(e,t){const n=e._x,i=e._y,r=e._z,o=e._w,a=t._x,l=t._y,c=t._z,h=t._w;return this._x=n*h+o*a+i*c-r*l,this._y=i*h+o*l+r*a-n*c,this._z=r*h+o*c+n*l-i*a,this._w=o*h-n*a-i*l-r*c,this._onChangeCallback(),this}slerp(e,t){if(t===0)return this;if(t===1)return this.copy(e);const n=this._x,i=this._y,r=this._z,o=this._w;let a=o*e._w+n*e._x+i*e._y+r*e._z;if(a<0?(this._w=-e._w,this._x=-e._x,this._y=-e._y,this._z=-e._z,a=-a):this.copy(e),a>=1)return this._w=o,this._x=n,this._y=i,this._z=r,this;const l=1-a*a;if(l<=Number.EPSILON){const f=1-t;return this._w=f*o+t*this._w,this._x=f*n+t*this._x,this._y=f*i+t*this._y,this._z=f*r+t*this._z,this.normalize(),this}const c=Math.sqrt(l),h=Math.atan2(c,a),u=Math.sin((1-t)*h)/c,d=Math.sin(t*h)/c;return this._w=o*u+this._w*d,this._x=n*u+this._x*d,this._y=i*u+this._y*d,this._z=r*u+this._z*d,this._onChangeCallback(),this}slerpQuaternions(e,t,n){return this.copy(e).slerp(t,n)}random(){const e=2*Math.PI*Math.random(),t=2*Math.PI*Math.random(),n=Math.random(),i=Math.sqrt(1-n),r=Math.sqrt(n);return this.set(i*Math.sin(e),i*Math.cos(e),r*Math.sin(t),r*Math.cos(t))}equals(e){return e._x===this._x&&e._y===this._y&&e._z===this._z&&e._w===this._w}fromArray(e,t=0){return this._x=e[t],this._y=e[t+1],this._z=e[t+2],this._w=e[t+3],this._onChangeCallback(),this}toArray(e=[],t=0){return e[t]=this._x,e[t+1]=this._y,e[t+2]=this._z,e[t+3]=this._w,e}fromBufferAttribute(e,t){return this._x=e.getX(t),this._y=e.getY(t),this._z=e.getZ(t),this._w=e.getW(t),this._onChangeCallback(),this}toJSON(){return this.toArray()}_onChange(e){return this._onChangeCallback=e,this}_onChangeCallback(){}*[Symbol.iterator](){yield this._x,yield this._y,yield this._z,yield this._w}}class w{constructor(e=0,t=0,n=0){w.prototype.isVector3=!0,this.x=e,this.y=t,this.z=n}set(e,t,n){return n===void 0&&(n=this.z),this.x=e,this.y=t,this.z=n,this}setScalar(e){return this.x=e,this.y=e,this.z=e,this}setX(e){return this.x=e,this}setY(e){return this.y=e,this}setZ(e){return this.z=e,this}setComponent(e,t){switch(e){case 0:this.x=t;break;case 1:this.y=t;break;case 2:this.z=t;break;default:throw new Error("index is out of range: "+e)}return this}getComponent(e){switch(e){case 0:return this.x;case 1:return this.y;case 2:return this.z;default:throw new Error("index is out of range: "+e)}}clone(){return new this.constructor(this.x,this.y,this.z)}copy(e){return this.x=e.x,this.y=e.y,this.z=e.z,this}add(e){return this.x+=e.x,this.y+=e.y,this.z+=e.z,this}addScalar(e){return this.x+=e,this.y+=e,this.z+=e,this}addVectors(e,t){return this.x=e.x+t.x,this.y=e.y+t.y,this.z=e.z+t.z,this}addScaledVector(e,t){return this.x+=e.x*t,this.y+=e.y*t,this.z+=e.z*t,this}sub(e){return this.x-=e.x,this.y-=e.y,this.z-=e.z,this}subScalar(e){return this.x-=e,this.y-=e,this.z-=e,this}subVectors(e,t){return this.x=e.x-t.x,this.y=e.y-t.y,this.z=e.z-t.z,this}multiply(e){return this.x*=e.x,this.y*=e.y,this.z*=e.z,this}multiplyScalar(e){return this.x*=e,this.y*=e,this.z*=e,this}multiplyVectors(e,t){return this.x=e.x*t.x,this.y=e.y*t.y,this.z=e.z*t.z,this}applyEuler(e){return this.applyQuaternion(Nl.setFromEuler(e))}applyAxisAngle(e,t){return this.applyQuaternion(Nl.setFromAxisAngle(e,t))}applyMatrix3(e){const t=this.x,n=this.y,i=this.z,r=e.elements;return this.x=r[0]*t+r[3]*n+r[6]*i,this.y=r[1]*t+r[4]*n+r[7]*i,this.z=r[2]*t+r[5]*n+r[8]*i,this}applyNormalMatrix(e){return this.applyMatrix3(e).normalize()}applyMatrix4(e){const t=this.x,n=this.y,i=this.z,r=e.elements,o=1/(r[3]*t+r[7]*n+r[11]*i+r[15]);return this.x=(r[0]*t+r[4]*n+r[8]*i+r[12])*o,this.y=(r[1]*t+r[5]*n+r[9]*i+r[13])*o,this.z=(r[2]*t+r[6]*n+r[10]*i+r[14])*o,this}applyQuaternion(e){const t=this.x,n=this.y,i=this.z,r=e.x,o=e.y,a=e.z,l=e.w,c=2*(o*i-a*n),h=2*(a*t-r*i),u=2*(r*n-o*t);return this.x=t+l*c+o*u-a*h,this.y=n+l*h+a*c-r*u,this.z=i+l*u+r*h-o*c,this}project(e){return this.applyMatrix4(e.matrixWorldInverse).applyMatrix4(e.projectionMatrix)}unproject(e){return this.applyMatrix4(e.projectionMatrixInverse).applyMatrix4(e.matrixWorld)}transformDirection(e){const t=this.x,n=this.y,i=this.z,r=e.elements;return this.x=r[0]*t+r[4]*n+r[8]*i,this.y=r[1]*t+r[5]*n+r[9]*i,this.z=r[2]*t+r[6]*n+r[10]*i,this.normalize()}divide(e){return this.x/=e.x,this.y/=e.y,this.z/=e.z,this}divideScalar(e){return this.multiplyScalar(1/e)}min(e){return this.x=Math.min(this.x,e.x),this.y=Math.min(this.y,e.y),this.z=Math.min(this.z,e.z),this}max(e){return this.x=Math.max(this.x,e.x),this.y=Math.max(this.y,e.y),this.z=Math.max(this.z,e.z),this}clamp(e,t){return this.x=Math.max(e.x,Math.min(t.x,this.x)),this.y=Math.max(e.y,Math.min(t.y,this.y)),this.z=Math.max(e.z,Math.min(t.z,this.z)),this}clampScalar(e,t){return this.x=Math.max(e,Math.min(t,this.x)),this.y=Math.max(e,Math.min(t,this.y)),this.z=Math.max(e,Math.min(t,this.z)),this}clampLength(e,t){const n=this.length();return this.divideScalar(n||1).multiplyScalar(Math.max(e,Math.min(t,n)))}floor(){return this.x=Math.floor(this.x),this.y=Math.floor(this.y),this.z=Math.floor(this.z),this}ceil(){return this.x=Math.ceil(this.x),this.y=Math.ceil(this.y),this.z=Math.ceil(this.z),this}round(){return this.x=Math.round(this.x),this.y=Math.round(this.y),this.z=Math.round(this.z),this}roundToZero(){return this.x=Math.trunc(this.x),this.y=Math.trunc(this.y),this.z=Math.trunc(this.z),this}negate(){return this.x=-this.x,this.y=-this.y,this.z=-this.z,this}dot(e){return this.x*e.x+this.y*e.y+this.z*e.z}lengthSq(){return this.x*this.x+this.y*this.y+this.z*this.z}length(){return Math.sqrt(this.x*this.x+this.y*this.y+this.z*this.z)}manhattanLength(){return Math.abs(this.x)+Math.abs(this.y)+Math.abs(this.z)}normalize(){return this.divideScalar(this.length()||1)}setLength(e){return this.normalize().multiplyScalar(e)}lerp(e,t){return this.x+=(e.x-this.x)*t,this.y+=(e.y-this.y)*t,this.z+=(e.z-this.z)*t,this}lerpVectors(e,t,n){return this.x=e.x+(t.x-e.x)*n,this.y=e.y+(t.y-e.y)*n,this.z=e.z+(t.z-e.z)*n,this}cross(e){return this.crossVectors(this,e)}crossVectors(e,t){const n=e.x,i=e.y,r=e.z,o=t.x,a=t.y,l=t.z;return this.x=i*l-r*a,this.y=r*o-n*l,this.z=n*a-i*o,this}projectOnVector(e){const t=e.lengthSq();if(t===0)return this.set(0,0,0);const n=e.dot(this)/t;return this.copy(e).multiplyScalar(n)}projectOnPlane(e){return lo.copy(this).projectOnVector(e),this.sub(lo)}reflect(e){return this.sub(lo.copy(e).multiplyScalar(2*this.dot(e)))}angleTo(e){const t=Math.sqrt(this.lengthSq()*e.lengthSq());if(t===0)return Math.PI/2;const n=this.dot(e)/t;return Math.acos(Tt(n,-1,1))}distanceTo(e){return Math.sqrt(this.distanceToSquared(e))}distanceToSquared(e){const t=this.x-e.x,n=this.y-e.y,i=this.z-e.z;return t*t+n*n+i*i}manhattanDistanceTo(e){return Math.abs(this.x-e.x)+Math.abs(this.y-e.y)+Math.abs(this.z-e.z)}setFromSpherical(e){return this.setFromSphericalCoords(e.radius,e.phi,e.theta)}setFromSphericalCoords(e,t,n){const i=Math.sin(t)*e;return this.x=i*Math.sin(n),this.y=Math.cos(t)*e,this.z=i*Math.cos(n),this}setFromCylindrical(e){return this.setFromCylindricalCoords(e.radius,e.theta,e.y)}setFromCylindricalCoords(e,t,n){return this.x=e*Math.sin(t),this.y=n,this.z=e*Math.cos(t),this}setFromMatrixPosition(e){const t=e.elements;return this.x=t[12],this.y=t[13],this.z=t[14],this}setFromMatrixScale(e){const t=this.setFromMatrixColumn(e,0).length(),n=this.setFromMatrixColumn(e,1).length(),i=this.setFromMatrixColumn(e,2).length();return this.x=t,this.y=n,this.z=i,this}setFromMatrixColumn(e,t){return this.fromArray(e.elements,t*4)}setFromMatrix3Column(e,t){return this.fromArray(e.elements,t*3)}setFromEuler(e){return this.x=e._x,this.y=e._y,this.z=e._z,this}setFromColor(e){return this.x=e.r,this.y=e.g,this.z=e.b,this}equals(e){return e.x===this.x&&e.y===this.y&&e.z===this.z}fromArray(e,t=0){return this.x=e[t],this.y=e[t+1],this.z=e[t+2],this}toArray(e=[],t=0){return e[t]=this.x,e[t+1]=this.y,e[t+2]=this.z,e}fromBufferAttribute(e,t){return this.x=e.getX(t),this.y=e.getY(t),this.z=e.getZ(t),this}random(){return this.x=Math.random(),this.y=Math.random(),this.z=Math.random(),this}randomDirection(){const e=Math.random()*Math.PI*2,t=Math.random()*2-1,n=Math.sqrt(1-t*t);return this.x=n*Math.cos(e),this.y=t,this.z=n*Math.sin(e),this}*[Symbol.iterator](){yield this.x,yield this.y,yield this.z}}const lo=new w,Nl=new Pt;class Lt{constructor(e=new w(1/0,1/0,1/0),t=new w(-1/0,-1/0,-1/0)){this.isBox3=!0,this.min=e,this.max=t}set(e,t){return this.min.copy(e),this.max.copy(t),this}setFromArray(e){this.makeEmpty();for(let t=0,n=e.length;t<n;t+=3)this.expandByPoint(fn.fromArray(e,t));return this}setFromBufferAttribute(e){this.makeEmpty();for(let t=0,n=e.count;t<n;t++)this.expandByPoint(fn.fromBufferAttribute(e,t));return this}setFromPoints(e){this.makeEmpty();for(let t=0,n=e.length;t<n;t++)this.expandByPoint(e[t]);return this}setFromCenterAndSize(e,t){const n=fn.copy(t).multiplyScalar(.5);return this.min.copy(e).sub(n),this.max.copy(e).add(n),this}setFromObject(e,t=!1){return this.makeEmpty(),this.expandByObject(e,t)}clone(){return new this.constructor().copy(this)}copy(e){return this.min.copy(e.min),this.max.copy(e.max),this}makeEmpty(){return this.min.x=this.min.y=this.min.z=1/0,this.max.x=this.max.y=this.max.z=-1/0,this}isEmpty(){return this.max.x<this.min.x||this.max.y<this.min.y||this.max.z<this.min.z}getCenter(e){return this.isEmpty()?e.set(0,0,0):e.addVectors(this.min,this.max).multiplyScalar(.5)}getSize(e){return this.isEmpty()?e.set(0,0,0):e.subVectors(this.max,this.min)}expandByPoint(e){return this.min.min(e),this.max.max(e),this}expandByVector(e){return this.min.sub(e),this.max.add(e),this}expandByScalar(e){return this.min.addScalar(-e),this.max.addScalar(e),this}expandByObject(e,t=!1){e.updateWorldMatrix(!1,!1);const n=e.geometry;if(n!==void 0){const r=n.getAttribute("position");if(t===!0&&r!==void 0&&e.isInstancedMesh!==!0)for(let o=0,a=r.count;o<a;o++)e.isMesh===!0?e.getVertexPosition(o,fn):fn.fromBufferAttribute(r,o),fn.applyMatrix4(e.matrixWorld),this.expandByPoint(fn);else e.boundingBox!==void 0?(e.boundingBox===null&&e.computeBoundingBox(),Gs.copy(e.boundingBox)):(n.boundingBox===null&&n.computeBoundingBox(),Gs.copy(n.boundingBox)),Gs.applyMatrix4(e.matrixWorld),this.union(Gs)}const i=e.children;for(let r=0,o=i.length;r<o;r++)this.expandByObject(i[r],t);return this}containsPoint(e){return e.x>=this.min.x&&e.x<=this.max.x&&e.y>=this.min.y&&e.y<=this.max.y&&e.z>=this.min.z&&e.z<=this.max.z}containsBox(e){return this.min.x<=e.min.x&&e.max.x<=this.max.x&&this.min.y<=e.min.y&&e.max.y<=this.max.y&&this.min.z<=e.min.z&&e.max.z<=this.max.z}getParameter(e,t){return t.set((e.x-this.min.x)/(this.max.x-this.min.x),(e.y-this.min.y)/(this.max.y-this.min.y),(e.z-this.min.z)/(this.max.z-this.min.z))}intersectsBox(e){return e.max.x>=this.min.x&&e.min.x<=this.max.x&&e.max.y>=this.min.y&&e.min.y<=this.max.y&&e.max.z>=this.min.z&&e.min.z<=this.max.z}intersectsSphere(e){return this.clampPoint(e.center,fn),fn.distanceToSquared(e.center)<=e.radius*e.radius}intersectsPlane(e){let t,n;return e.normal.x>0?(t=e.normal.x*this.min.x,n=e.normal.x*this.max.x):(t=e.normal.x*this.max.x,n=e.normal.x*this.min.x),e.normal.y>0?(t+=e.normal.y*this.min.y,n+=e.normal.y*this.max.y):(t+=e.normal.y*this.max.y,n+=e.normal.y*this.min.y),e.normal.z>0?(t+=e.normal.z*this.min.z,n+=e.normal.z*this.max.z):(t+=e.normal.z*this.max.z,n+=e.normal.z*this.min.z),t<=-e.constant&&n>=-e.constant}intersectsTriangle(e){if(this.isEmpty())return!1;this.getCenter(ds),Ws.subVectors(this.max,ds),Ci.subVectors(e.a,ds),Pi.subVectors(e.b,ds),Ri.subVectors(e.c,ds),Wn.subVectors(Pi,Ci),Xn.subVectors(Ri,Pi),si.subVectors(Ci,Ri);let t=[0,-Wn.z,Wn.y,0,-Xn.z,Xn.y,0,-si.z,si.y,Wn.z,0,-Wn.x,Xn.z,0,-Xn.x,si.z,0,-si.x,-Wn.y,Wn.x,0,-Xn.y,Xn.x,0,-si.y,si.x,0];return!co(t,Ci,Pi,Ri,Ws)||(t=[1,0,0,0,1,0,0,0,1],!co(t,Ci,Pi,Ri,Ws))?!1:(Xs.crossVectors(Wn,Xn),t=[Xs.x,Xs.y,Xs.z],co(t,Ci,Pi,Ri,Ws))}clampPoint(e,t){return t.copy(e).clamp(this.min,this.max)}distanceToPoint(e){return this.clampPoint(e,fn).distanceTo(e)}getBoundingSphere(e){return this.isEmpty()?e.makeEmpty():(this.getCenter(e.center),e.radius=this.getSize(fn).length()*.5),e}intersect(e){return this.min.max(e.min),this.max.min(e.max),this.isEmpty()&&this.makeEmpty(),this}union(e){return this.min.min(e.min),this.max.max(e.max),this}applyMatrix4(e){return this.isEmpty()?this:(Pn[0].set(this.min.x,this.min.y,this.min.z).applyMatrix4(e),Pn[1].set(this.min.x,this.min.y,this.max.z).applyMatrix4(e),Pn[2].set(this.min.x,this.max.y,this.min.z).applyMatrix4(e),Pn[3].set(this.min.x,this.max.y,this.max.z).applyMatrix4(e),Pn[4].set(this.max.x,this.min.y,this.min.z).applyMatrix4(e),Pn[5].set(this.max.x,this.min.y,this.max.z).applyMatrix4(e),Pn[6].set(this.max.x,this.max.y,this.min.z).applyMatrix4(e),Pn[7].set(this.max.x,this.max.y,this.max.z).applyMatrix4(e),this.setFromPoints(Pn),this)}translate(e){return this.min.add(e),this.max.add(e),this}equals(e){return e.min.equals(this.min)&&e.max.equals(this.max)}}const Pn=[new w,new w,new w,new w,new w,new w,new w,new w],fn=new w,Gs=new Lt,Ci=new w,Pi=new w,Ri=new w,Wn=new w,Xn=new w,si=new w,ds=new w,Ws=new w,Xs=new w,ri=new w;function co(s,e,t,n,i){for(let r=0,o=s.length-3;r<=o;r+=3){ri.fromArray(s,r);const a=i.x*Math.abs(ri.x)+i.y*Math.abs(ri.y)+i.z*Math.abs(ri.z),l=e.dot(ri),c=t.dot(ri),h=n.dot(ri);if(Math.max(-Math.max(l,c,h),Math.min(l,c,h))>a)return!1}return!0}const Id=new Lt,fs=new w,ho=new w;class Mi{constructor(e=new w,t=-1){this.isSphere=!0,this.center=e,this.radius=t}set(e,t){return this.center.copy(e),this.radius=t,this}setFromPoints(e,t){const n=this.center;t!==void 0?n.copy(t):Id.setFromPoints(e).getCenter(n);let i=0;for(let r=0,o=e.length;r<o;r++)i=Math.max(i,n.distanceToSquared(e[r]));return this.radius=Math.sqrt(i),this}copy(e){return this.center.copy(e.center),this.radius=e.radius,this}isEmpty(){return this.radius<0}makeEmpty(){return this.center.set(0,0,0),this.radius=-1,this}containsPoint(e){return e.distanceToSquared(this.center)<=this.radius*this.radius}distanceToPoint(e){return e.distanceTo(this.center)-this.radius}intersectsSphere(e){const t=this.radius+e.radius;return e.center.distanceToSquared(this.center)<=t*t}intersectsBox(e){return e.intersectsSphere(this)}intersectsPlane(e){return Math.abs(e.distanceToPoint(this.center))<=this.radius}clampPoint(e,t){const n=this.center.distanceToSquared(e);return t.copy(e),n>this.radius*this.radius&&(t.sub(this.center).normalize(),t.multiplyScalar(this.radius).add(this.center)),t}getBoundingBox(e){return this.isEmpty()?(e.makeEmpty(),e):(e.set(this.center,this.center),e.expandByScalar(this.radius),e)}applyMatrix4(e){return this.center.applyMatrix4(e),this.radius=this.radius*e.getMaxScaleOnAxis(),this}translate(e){return this.center.add(e),this}expandByPoint(e){if(this.isEmpty())return this.center.copy(e),this.radius=0,this;fs.subVectors(e,this.center);const t=fs.lengthSq();if(t>this.radius*this.radius){const n=Math.sqrt(t),i=(n-this.radius)*.5;this.center.addScaledVector(fs,i/n),this.radius+=i}return this}union(e){return e.isEmpty()?this:this.isEmpty()?(this.copy(e),this):(this.center.equals(e.center)===!0?this.radius=Math.max(this.radius,e.radius):(ho.subVectors(e.center,this.center).setLength(e.radius),this.expandByPoint(fs.copy(e.center).add(ho)),this.expandByPoint(fs.copy(e.center).sub(ho))),this)}equals(e){return e.center.equals(this.center)&&e.radius===this.radius}clone(){return new this.constructor().copy(this)}}const Rn=new w,uo=new w,Ys=new w,Yn=new w,fo=new w,qs=new w,po=new w;class bi{constructor(e=new w,t=new w(0,0,-1)){this.origin=e,this.direction=t}set(e,t){return this.origin.copy(e),this.direction.copy(t),this}copy(e){return this.origin.copy(e.origin),this.direction.copy(e.direction),this}at(e,t){return t.copy(this.origin).addScaledVector(this.direction,e)}lookAt(e){return this.direction.copy(e).sub(this.origin).normalize(),this}recast(e){return this.origin.copy(this.at(e,Rn)),this}closestPointToPoint(e,t){t.subVectors(e,this.origin);const n=t.dot(this.direction);return n<0?t.copy(this.origin):t.copy(this.origin).addScaledVector(this.direction,n)}distanceToPoint(e){return Math.sqrt(this.distanceSqToPoint(e))}distanceSqToPoint(e){const t=Rn.subVectors(e,this.origin).dot(this.direction);return t<0?this.origin.distanceToSquared(e):(Rn.copy(this.origin).addScaledVector(this.direction,t),Rn.distanceToSquared(e))}distanceSqToSegment(e,t,n,i){uo.copy(e).add(t).multiplyScalar(.5),Ys.copy(t).sub(e).normalize(),Yn.copy(this.origin).sub(uo);const r=e.distanceTo(t)*.5,o=-this.direction.dot(Ys),a=Yn.dot(this.direction),l=-Yn.dot(Ys),c=Yn.lengthSq(),h=Math.abs(1-o*o);let u,d,f,g;if(h>0)if(u=o*l-a,d=o*a-l,g=r*h,u>=0)if(d>=-g)if(d<=g){const x=1/h;u*=x,d*=x,f=u*(u+o*d+2*a)+d*(o*u+d+2*l)+c}else d=r,u=Math.max(0,-(o*d+a)),f=-u*u+d*(d+2*l)+c;else d=-r,u=Math.max(0,-(o*d+a)),f=-u*u+d*(d+2*l)+c;else d<=-g?(u=Math.max(0,-(-o*r+a)),d=u>0?-r:Math.min(Math.max(-r,-l),r),f=-u*u+d*(d+2*l)+c):d<=g?(u=0,d=Math.min(Math.max(-r,-l),r),f=d*(d+2*l)+c):(u=Math.max(0,-(o*r+a)),d=u>0?r:Math.min(Math.max(-r,-l),r),f=-u*u+d*(d+2*l)+c);else d=o>0?-r:r,u=Math.max(0,-(o*d+a)),f=-u*u+d*(d+2*l)+c;return n&&n.copy(this.origin).addScaledVector(this.direction,u),i&&i.copy(uo).addScaledVector(Ys,d),f}intersectSphere(e,t){Rn.subVectors(e.center,this.origin);const n=Rn.dot(this.direction),i=Rn.dot(Rn)-n*n,r=e.radius*e.radius;if(i>r)return null;const o=Math.sqrt(r-i),a=n-o,l=n+o;return l<0?null:a<0?this.at(l,t):this.at(a,t)}intersectsSphere(e){return this.distanceSqToPoint(e.center)<=e.radius*e.radius}distanceToPlane(e){const t=e.normal.dot(this.direction);if(t===0)return e.distanceToPoint(this.origin)===0?0:null;const n=-(this.origin.dot(e.normal)+e.constant)/t;return n>=0?n:null}intersectPlane(e,t){const n=this.distanceToPlane(e);return n===null?null:this.at(n,t)}intersectsPlane(e){const t=e.distanceToPoint(this.origin);return t===0||e.normal.dot(this.direction)*t<0}intersectBox(e,t){let n,i,r,o,a,l;const c=1/this.direction.x,h=1/this.direction.y,u=1/this.direction.z,d=this.origin;return c>=0?(n=(e.min.x-d.x)*c,i=(e.max.x-d.x)*c):(n=(e.max.x-d.x)*c,i=(e.min.x-d.x)*c),h>=0?(r=(e.min.y-d.y)*h,o=(e.max.y-d.y)*h):(r=(e.max.y-d.y)*h,o=(e.min.y-d.y)*h),n>o||r>i||((r>n||isNaN(n))&&(n=r),(o<i||isNaN(i))&&(i=o),u>=0?(a=(e.min.z-d.z)*u,l=(e.max.z-d.z)*u):(a=(e.max.z-d.z)*u,l=(e.min.z-d.z)*u),n>l||a>i)||((a>n||n!==n)&&(n=a),(l<i||i!==i)&&(i=l),i<0)?null:this.at(n>=0?n:i,t)}intersectsBox(e){return this.intersectBox(e,Rn)!==null}intersectTriangle(e,t,n,i,r){fo.subVectors(t,e),qs.subVectors(n,e),po.crossVectors(fo,qs);let o=this.direction.dot(po),a;if(o>0){if(i)return null;a=1}else if(o<0)a=-1,o=-o;else return null;Yn.subVectors(this.origin,e);const l=a*this.direction.dot(qs.crossVectors(Yn,qs));if(l<0)return null;const c=a*this.direction.dot(fo.cross(Yn));if(c<0||l+c>o)return null;const h=-a*Yn.dot(po);return h<0?null:this.at(h/o,r)}applyMatrix4(e){return this.origin.applyMatrix4(e),this.direction.transformDirection(e),this}equals(e){return e.origin.equals(this.origin)&&e.direction.equals(this.direction)}clone(){return new this.constructor().copy(this)}}class Fe{constructor(e,t,n,i,r,o,a,l,c,h,u,d,f,g,x,p){Fe.prototype.isMatrix4=!0,this.elements=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1],e!==void 0&&this.set(e,t,n,i,r,o,a,l,c,h,u,d,f,g,x,p)}set(e,t,n,i,r,o,a,l,c,h,u,d,f,g,x,p){const m=this.elements;return m[0]=e,m[4]=t,m[8]=n,m[12]=i,m[1]=r,m[5]=o,m[9]=a,m[13]=l,m[2]=c,m[6]=h,m[10]=u,m[14]=d,m[3]=f,m[7]=g,m[11]=x,m[15]=p,this}identity(){return this.set(1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1),this}clone(){return new Fe().fromArray(this.elements)}copy(e){const t=this.elements,n=e.elements;return t[0]=n[0],t[1]=n[1],t[2]=n[2],t[3]=n[3],t[4]=n[4],t[5]=n[5],t[6]=n[6],t[7]=n[7],t[8]=n[8],t[9]=n[9],t[10]=n[10],t[11]=n[11],t[12]=n[12],t[13]=n[13],t[14]=n[14],t[15]=n[15],this}copyPosition(e){const t=this.elements,n=e.elements;return t[12]=n[12],t[13]=n[13],t[14]=n[14],this}setFromMatrix3(e){const t=e.elements;return this.set(t[0],t[3],t[6],0,t[1],t[4],t[7],0,t[2],t[5],t[8],0,0,0,0,1),this}extractBasis(e,t,n){return e.setFromMatrixColumn(this,0),t.setFromMatrixColumn(this,1),n.setFromMatrixColumn(this,2),this}makeBasis(e,t,n){return this.set(e.x,t.x,n.x,0,e.y,t.y,n.y,0,e.z,t.z,n.z,0,0,0,0,1),this}extractRotation(e){const t=this.elements,n=e.elements,i=1/Di.setFromMatrixColumn(e,0).length(),r=1/Di.setFromMatrixColumn(e,1).length(),o=1/Di.setFromMatrixColumn(e,2).length();return t[0]=n[0]*i,t[1]=n[1]*i,t[2]=n[2]*i,t[3]=0,t[4]=n[4]*r,t[5]=n[5]*r,t[6]=n[6]*r,t[7]=0,t[8]=n[8]*o,t[9]=n[9]*o,t[10]=n[10]*o,t[11]=0,t[12]=0,t[13]=0,t[14]=0,t[15]=1,this}makeRotationFromEuler(e){const t=this.elements,n=e.x,i=e.y,r=e.z,o=Math.cos(n),a=Math.sin(n),l=Math.cos(i),c=Math.sin(i),h=Math.cos(r),u=Math.sin(r);if(e.order==="XYZ"){const d=o*h,f=o*u,g=a*h,x=a*u;t[0]=l*h,t[4]=-l*u,t[8]=c,t[1]=f+g*c,t[5]=d-x*c,t[9]=-a*l,t[2]=x-d*c,t[6]=g+f*c,t[10]=o*l}else if(e.order==="YXZ"){const d=l*h,f=l*u,g=c*h,x=c*u;t[0]=d+x*a,t[4]=g*a-f,t[8]=o*c,t[1]=o*u,t[5]=o*h,t[9]=-a,t[2]=f*a-g,t[6]=x+d*a,t[10]=o*l}else if(e.order==="ZXY"){const d=l*h,f=l*u,g=c*h,x=c*u;t[0]=d-x*a,t[4]=-o*u,t[8]=g+f*a,t[1]=f+g*a,t[5]=o*h,t[9]=x-d*a,t[2]=-o*c,t[6]=a,t[10]=o*l}else if(e.order==="ZYX"){const d=o*h,f=o*u,g=a*h,x=a*u;t[0]=l*h,t[4]=g*c-f,t[8]=d*c+x,t[1]=l*u,t[5]=x*c+d,t[9]=f*c-g,t[2]=-c,t[6]=a*l,t[10]=o*l}else if(e.order==="YZX"){const d=o*l,f=o*c,g=a*l,x=a*c;t[0]=l*h,t[4]=x-d*u,t[8]=g*u+f,t[1]=u,t[5]=o*h,t[9]=-a*h,t[2]=-c*h,t[6]=f*u+g,t[10]=d-x*u}else if(e.order==="XZY"){const d=o*l,f=o*c,g=a*l,x=a*c;t[0]=l*h,t[4]=-u,t[8]=c*h,t[1]=d*u+x,t[5]=o*h,t[9]=f*u-g,t[2]=g*u-f,t[6]=a*h,t[10]=x*u+d}return t[3]=0,t[7]=0,t[11]=0,t[12]=0,t[13]=0,t[14]=0,t[15]=1,this}makeRotationFromQuaternion(e){return this.compose(Ld,e,Nd)}lookAt(e,t,n){const i=this.elements;return tn.subVectors(e,t),tn.lengthSq()===0&&(tn.z=1),tn.normalize(),qn.crossVectors(n,tn),qn.lengthSq()===0&&(Math.abs(n.z)===1?tn.x+=1e-4:tn.z+=1e-4,tn.normalize(),qn.crossVectors(n,tn)),qn.normalize(),js.crossVectors(tn,qn),i[0]=qn.x,i[4]=js.x,i[8]=tn.x,i[1]=qn.y,i[5]=js.y,i[9]=tn.y,i[2]=qn.z,i[6]=js.z,i[10]=tn.z,this}multiply(e){return this.multiplyMatrices(this,e)}premultiply(e){return this.multiplyMatrices(e,this)}multiplyMatrices(e,t){const n=e.elements,i=t.elements,r=this.elements,o=n[0],a=n[4],l=n[8],c=n[12],h=n[1],u=n[5],d=n[9],f=n[13],g=n[2],x=n[6],p=n[10],m=n[14],_=n[3],v=n[7],M=n[11],S=n[15],E=i[0],C=i[4],z=i[8],T=i[12],y=i[1],b=i[5],D=i[9],L=i[13],N=i[2],B=i[6],k=i[10],q=i[14],U=i[3],V=i[7],P=i[11],O=i[15];return r[0]=o*E+a*y+l*N+c*U,r[4]=o*C+a*b+l*B+c*V,r[8]=o*z+a*D+l*k+c*P,r[12]=o*T+a*L+l*q+c*O,r[1]=h*E+u*y+d*N+f*U,r[5]=h*C+u*b+d*B+f*V,r[9]=h*z+u*D+d*k+f*P,r[13]=h*T+u*L+d*q+f*O,r[2]=g*E+x*y+p*N+m*U,r[6]=g*C+x*b+p*B+m*V,r[10]=g*z+x*D+p*k+m*P,r[14]=g*T+x*L+p*q+m*O,r[3]=_*E+v*y+M*N+S*U,r[7]=_*C+v*b+M*B+S*V,r[11]=_*z+v*D+M*k+S*P,r[15]=_*T+v*L+M*q+S*O,this}multiplyScalar(e){const t=this.elements;return t[0]*=e,t[4]*=e,t[8]*=e,t[12]*=e,t[1]*=e,t[5]*=e,t[9]*=e,t[13]*=e,t[2]*=e,t[6]*=e,t[10]*=e,t[14]*=e,t[3]*=e,t[7]*=e,t[11]*=e,t[15]*=e,this}determinant(){const e=this.elements,t=e[0],n=e[4],i=e[8],r=e[12],o=e[1],a=e[5],l=e[9],c=e[13],h=e[2],u=e[6],d=e[10],f=e[14],g=e[3],x=e[7],p=e[11],m=e[15];return g*(+r*l*u-i*c*u-r*a*d+n*c*d+i*a*f-n*l*f)+x*(+t*l*f-t*c*d+r*o*d-i*o*f+i*c*h-r*l*h)+p*(+t*c*u-t*a*f-r*o*u+n*o*f+r*a*h-n*c*h)+m*(-i*a*h-t*l*u+t*a*d+i*o*u-n*o*d+n*l*h)}transpose(){const e=this.elements;let t;return t=e[1],e[1]=e[4],e[4]=t,t=e[2],e[2]=e[8],e[8]=t,t=e[6],e[6]=e[9],e[9]=t,t=e[3],e[3]=e[12],e[12]=t,t=e[7],e[7]=e[13],e[13]=t,t=e[11],e[11]=e[14],e[14]=t,this}setPosition(e,t,n){const i=this.elements;return e.isVector3?(i[12]=e.x,i[13]=e.y,i[14]=e.z):(i[12]=e,i[13]=t,i[14]=n),this}invert(){const e=this.elements,t=e[0],n=e[1],i=e[2],r=e[3],o=e[4],a=e[5],l=e[6],c=e[7],h=e[8],u=e[9],d=e[10],f=e[11],g=e[12],x=e[13],p=e[14],m=e[15],_=u*p*c-x*d*c+x*l*f-a*p*f-u*l*m+a*d*m,v=g*d*c-h*p*c-g*l*f+o*p*f+h*l*m-o*d*m,M=h*x*c-g*u*c+g*a*f-o*x*f-h*a*m+o*u*m,S=g*u*l-h*x*l-g*a*d+o*x*d+h*a*p-o*u*p,E=t*_+n*v+i*M+r*S;if(E===0)return this.set(0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0);const C=1/E;return e[0]=_*C,e[1]=(x*d*r-u*p*r-x*i*f+n*p*f+u*i*m-n*d*m)*C,e[2]=(a*p*r-x*l*r+x*i*c-n*p*c-a*i*m+n*l*m)*C,e[3]=(u*l*r-a*d*r-u*i*c+n*d*c+a*i*f-n*l*f)*C,e[4]=v*C,e[5]=(h*p*r-g*d*r+g*i*f-t*p*f-h*i*m+t*d*m)*C,e[6]=(g*l*r-o*p*r-g*i*c+t*p*c+o*i*m-t*l*m)*C,e[7]=(o*d*r-h*l*r+h*i*c-t*d*c-o*i*f+t*l*f)*C,e[8]=M*C,e[9]=(g*u*r-h*x*r-g*n*f+t*x*f+h*n*m-t*u*m)*C,e[10]=(o*x*r-g*a*r+g*n*c-t*x*c-o*n*m+t*a*m)*C,e[11]=(h*a*r-o*u*r-h*n*c+t*u*c+o*n*f-t*a*f)*C,e[12]=S*C,e[13]=(h*x*i-g*u*i+g*n*d-t*x*d-h*n*p+t*u*p)*C,e[14]=(g*a*i-o*x*i-g*n*l+t*x*l+o*n*p-t*a*p)*C,e[15]=(o*u*i-h*a*i+h*n*l-t*u*l-o*n*d+t*a*d)*C,this}scale(e){const t=this.elements,n=e.x,i=e.y,r=e.z;return t[0]*=n,t[4]*=i,t[8]*=r,t[1]*=n,t[5]*=i,t[9]*=r,t[2]*=n,t[6]*=i,t[10]*=r,t[3]*=n,t[7]*=i,t[11]*=r,this}getMaxScaleOnAxis(){const e=this.elements,t=e[0]*e[0]+e[1]*e[1]+e[2]*e[2],n=e[4]*e[4]+e[5]*e[5]+e[6]*e[6],i=e[8]*e[8]+e[9]*e[9]+e[10]*e[10];return Math.sqrt(Math.max(t,n,i))}makeTranslation(e,t,n){return e.isVector3?this.set(1,0,0,e.x,0,1,0,e.y,0,0,1,e.z,0,0,0,1):this.set(1,0,0,e,0,1,0,t,0,0,1,n,0,0,0,1),this}makeRotationX(e){const t=Math.cos(e),n=Math.sin(e);return this.set(1,0,0,0,0,t,-n,0,0,n,t,0,0,0,0,1),this}makeRotationY(e){const t=Math.cos(e),n=Math.sin(e);return this.set(t,0,n,0,0,1,0,0,-n,0,t,0,0,0,0,1),this}makeRotationZ(e){const t=Math.cos(e),n=Math.sin(e);return this.set(t,-n,0,0,n,t,0,0,0,0,1,0,0,0,0,1),this}makeRotationAxis(e,t){const n=Math.cos(t),i=Math.sin(t),r=1-n,o=e.x,a=e.y,l=e.z,c=r*o,h=r*a;return this.set(c*o+n,c*a-i*l,c*l+i*a,0,c*a+i*l,h*a+n,h*l-i*o,0,c*l-i*a,h*l+i*o,r*l*l+n,0,0,0,0,1),this}makeScale(e,t,n){return this.set(e,0,0,0,0,t,0,0,0,0,n,0,0,0,0,1),this}makeShear(e,t,n,i,r,o){return this.set(1,n,r,0,e,1,o,0,t,i,1,0,0,0,0,1),this}compose(e,t,n){const i=this.elements,r=t._x,o=t._y,a=t._z,l=t._w,c=r+r,h=o+o,u=a+a,d=r*c,f=r*h,g=r*u,x=o*h,p=o*u,m=a*u,_=l*c,v=l*h,M=l*u,S=n.x,E=n.y,C=n.z;return i[0]=(1-(x+m))*S,i[1]=(f+M)*S,i[2]=(g-v)*S,i[3]=0,i[4]=(f-M)*E,i[5]=(1-(d+m))*E,i[6]=(p+_)*E,i[7]=0,i[8]=(g+v)*C,i[9]=(p-_)*C,i[10]=(1-(d+x))*C,i[11]=0,i[12]=e.x,i[13]=e.y,i[14]=e.z,i[15]=1,this}decompose(e,t,n){const i=this.elements;let r=Di.set(i[0],i[1],i[2]).length();const o=Di.set(i[4],i[5],i[6]).length(),a=Di.set(i[8],i[9],i[10]).length();this.determinant()<0&&(r=-r),e.x=i[12],e.y=i[13],e.z=i[14],pn.copy(this);const c=1/r,h=1/o,u=1/a;return pn.elements[0]*=c,pn.elements[1]*=c,pn.elements[2]*=c,pn.elements[4]*=h,pn.elements[5]*=h,pn.elements[6]*=h,pn.elements[8]*=u,pn.elements[9]*=u,pn.elements[10]*=u,t.setFromRotationMatrix(pn),n.x=r,n.y=o,n.z=a,this}makePerspective(e,t,n,i,r,o,a=zn){const l=this.elements,c=2*r/(t-e),h=2*r/(n-i),u=(t+e)/(t-e),d=(n+i)/(n-i);let f,g;if(a===zn)f=-(o+r)/(o-r),g=-2*o*r/(o-r);else if(a===Ur)f=-o/(o-r),g=-o*r/(o-r);else throw new Error("THREE.Matrix4.makePerspective(): Invalid coordinate system: "+a);return l[0]=c,l[4]=0,l[8]=u,l[12]=0,l[1]=0,l[5]=h,l[9]=d,l[13]=0,l[2]=0,l[6]=0,l[10]=f,l[14]=g,l[3]=0,l[7]=0,l[11]=-1,l[15]=0,this}makeOrthographic(e,t,n,i,r,o,a=zn){const l=this.elements,c=1/(t-e),h=1/(n-i),u=1/(o-r),d=(t+e)*c,f=(n+i)*h;let g,x;if(a===zn)g=(o+r)*u,x=-2*u;else if(a===Ur)g=r*u,x=-1*u;else throw new Error("THREE.Matrix4.makeOrthographic(): Invalid coordinate system: "+a);return l[0]=2*c,l[4]=0,l[8]=0,l[12]=-d,l[1]=0,l[5]=2*h,l[9]=0,l[13]=-f,l[2]=0,l[6]=0,l[10]=x,l[14]=-g,l[3]=0,l[7]=0,l[11]=0,l[15]=1,this}equals(e){const t=this.elements,n=e.elements;for(let i=0;i<16;i++)if(t[i]!==n[i])return!1;return!0}fromArray(e,t=0){for(let n=0;n<16;n++)this.elements[n]=e[n+t];return this}toArray(e=[],t=0){const n=this.elements;return e[t]=n[0],e[t+1]=n[1],e[t+2]=n[2],e[t+3]=n[3],e[t+4]=n[4],e[t+5]=n[5],e[t+6]=n[6],e[t+7]=n[7],e[t+8]=n[8],e[t+9]=n[9],e[t+10]=n[10],e[t+11]=n[11],e[t+12]=n[12],e[t+13]=n[13],e[t+14]=n[14],e[t+15]=n[15],e}}const Di=new w,pn=new Fe,Ld=new w(0,0,0),Nd=new w(1,1,1),qn=new w,js=new w,tn=new w,Ul=new Fe,Ol=new Pt;class Yt{constructor(e=0,t=0,n=0,i=Yt.DEFAULT_ORDER){this.isEuler=!0,this._x=e,this._y=t,this._z=n,this._order=i}get x(){return this._x}set x(e){this._x=e,this._onChangeCallback()}get y(){return this._y}set y(e){this._y=e,this._onChangeCallback()}get z(){return this._z}set z(e){this._z=e,this._onChangeCallback()}get order(){return this._order}set order(e){this._order=e,this._onChangeCallback()}set(e,t,n,i=this._order){return this._x=e,this._y=t,this._z=n,this._order=i,this._onChangeCallback(),this}clone(){return new this.constructor(this._x,this._y,this._z,this._order)}copy(e){return this._x=e._x,this._y=e._y,this._z=e._z,this._order=e._order,this._onChangeCallback(),this}setFromRotationMatrix(e,t=this._order,n=!0){const i=e.elements,r=i[0],o=i[4],a=i[8],l=i[1],c=i[5],h=i[9],u=i[2],d=i[6],f=i[10];switch(t){case"XYZ":this._y=Math.asin(Tt(a,-1,1)),Math.abs(a)<.9999999?(this._x=Math.atan2(-h,f),this._z=Math.atan2(-o,r)):(this._x=Math.atan2(d,c),this._z=0);break;case"YXZ":this._x=Math.asin(-Tt(h,-1,1)),Math.abs(h)<.9999999?(this._y=Math.atan2(a,f),this._z=Math.atan2(l,c)):(this._y=Math.atan2(-u,r),this._z=0);break;case"ZXY":this._x=Math.asin(Tt(d,-1,1)),Math.abs(d)<.9999999?(this._y=Math.atan2(-u,f),this._z=Math.atan2(-o,c)):(this._y=0,this._z=Math.atan2(l,r));break;case"ZYX":this._y=Math.asin(-Tt(u,-1,1)),Math.abs(u)<.9999999?(this._x=Math.atan2(d,f),this._z=Math.atan2(l,r)):(this._x=0,this._z=Math.atan2(-o,c));break;case"YZX":this._z=Math.asin(Tt(l,-1,1)),Math.abs(l)<.9999999?(this._x=Math.atan2(-h,c),this._y=Math.atan2(-u,r)):(this._x=0,this._y=Math.atan2(a,f));break;case"XZY":this._z=Math.asin(-Tt(o,-1,1)),Math.abs(o)<.9999999?(this._x=Math.atan2(d,c),this._y=Math.atan2(a,r)):(this._x=Math.atan2(-h,f),this._y=0);break;default:console.warn("THREE.Euler: .setFromRotationMatrix() encountered an unknown order: "+t)}return this._order=t,n===!0&&this._onChangeCallback(),this}setFromQuaternion(e,t,n){return Ul.makeRotationFromQuaternion(e),this.setFromRotationMatrix(Ul,t,n)}setFromVector3(e,t=this._order){return this.set(e.x,e.y,e.z,t)}reorder(e){return Ol.setFromEuler(this),this.setFromQuaternion(Ol,e)}equals(e){return e._x===this._x&&e._y===this._y&&e._z===this._z&&e._order===this._order}fromArray(e){return this._x=e[0],this._y=e[1],this._z=e[2],e[3]!==void 0&&(this._order=e[3]),this._onChangeCallback(),this}toArray(e=[],t=0){return e[t]=this._x,e[t+1]=this._y,e[t+2]=this._z,e[t+3]=this._order,e}_onChange(e){return this._onChangeCallback=e,this}_onChangeCallback(){}*[Symbol.iterator](){yield this._x,yield this._y,yield this._z,yield this._order}}Yt.DEFAULT_ORDER="XYZ";class Qa{constructor(){this.mask=1}set(e){this.mask=(1<<e|0)>>>0}enable(e){this.mask|=1<<e|0}enableAll(){this.mask=-1}toggle(e){this.mask^=1<<e|0}disable(e){this.mask&=~(1<<e|0)}disableAll(){this.mask=0}test(e){return(this.mask&e.mask)!==0}isEnabled(e){return(this.mask&(1<<e|0))!==0}}let Ud=0;const Fl=new w,Ii=new Pt,Dn=new Fe,Ks=new w,ps=new w,Od=new w,Fd=new Pt,zl=new w(1,0,0),kl=new w(0,1,0),Bl=new w(0,0,1),Vl={type:"added"},zd={type:"removed"},Li={type:"childadded",child:null},mo={type:"childremoved",child:null};class Mt extends _i{constructor(){super(),this.isObject3D=!0,Object.defineProperty(this,"id",{value:Ud++}),this.uuid=yi(),this.name="",this.type="Object3D",this.parent=null,this.children=[],this.up=Mt.DEFAULT_UP.clone();const e=new w,t=new Yt,n=new Pt,i=new w(1,1,1);function r(){n.setFromEuler(t,!1)}function o(){t.setFromQuaternion(n,void 0,!1)}t._onChange(r),n._onChange(o),Object.defineProperties(this,{position:{configurable:!0,enumerable:!0,value:e},rotation:{configurable:!0,enumerable:!0,value:t},quaternion:{configurable:!0,enumerable:!0,value:n},scale:{configurable:!0,enumerable:!0,value:i},modelViewMatrix:{value:new Fe},normalMatrix:{value:new Ye}}),this.matrix=new Fe,this.matrixWorld=new Fe,this.matrixAutoUpdate=Mt.DEFAULT_MATRIX_AUTO_UPDATE,this.matrixWorldAutoUpdate=Mt.DEFAULT_MATRIX_WORLD_AUTO_UPDATE,this.matrixWorldNeedsUpdate=!1,this.layers=new Qa,this.visible=!0,this.castShadow=!1,this.receiveShadow=!1,this.frustumCulled=!0,this.renderOrder=0,this.animations=[],this.userData={}}onBeforeShadow(){}onAfterShadow(){}onBeforeRender(){}onAfterRender(){}applyMatrix4(e){this.matrixAutoUpdate&&this.updateMatrix(),this.matrix.premultiply(e),this.matrix.decompose(this.position,this.quaternion,this.scale)}applyQuaternion(e){return this.quaternion.premultiply(e),this}setRotationFromAxisAngle(e,t){this.quaternion.setFromAxisAngle(e,t)}setRotationFromEuler(e){this.quaternion.setFromEuler(e,!0)}setRotationFromMatrix(e){this.quaternion.setFromRotationMatrix(e)}setRotationFromQuaternion(e){this.quaternion.copy(e)}rotateOnAxis(e,t){return Ii.setFromAxisAngle(e,t),this.quaternion.multiply(Ii),this}rotateOnWorldAxis(e,t){return Ii.setFromAxisAngle(e,t),this.quaternion.premultiply(Ii),this}rotateX(e){return this.rotateOnAxis(zl,e)}rotateY(e){return this.rotateOnAxis(kl,e)}rotateZ(e){return this.rotateOnAxis(Bl,e)}translateOnAxis(e,t){return Fl.copy(e).applyQuaternion(this.quaternion),this.position.add(Fl.multiplyScalar(t)),this}translateX(e){return this.translateOnAxis(zl,e)}translateY(e){return this.translateOnAxis(kl,e)}translateZ(e){return this.translateOnAxis(Bl,e)}localToWorld(e){return this.updateWorldMatrix(!0,!1),e.applyMatrix4(this.matrixWorld)}worldToLocal(e){return this.updateWorldMatrix(!0,!1),e.applyMatrix4(Dn.copy(this.matrixWorld).invert())}lookAt(e,t,n){e.isVector3?Ks.copy(e):Ks.set(e,t,n);const i=this.parent;this.updateWorldMatrix(!0,!1),ps.setFromMatrixPosition(this.matrixWorld),this.isCamera||this.isLight?Dn.lookAt(ps,Ks,this.up):Dn.lookAt(Ks,ps,this.up),this.quaternion.setFromRotationMatrix(Dn),i&&(Dn.extractRotation(i.matrixWorld),Ii.setFromRotationMatrix(Dn),this.quaternion.premultiply(Ii.invert()))}add(e){if(arguments.length>1){for(let t=0;t<arguments.length;t++)this.add(arguments[t]);return this}return e===this?(console.error("THREE.Object3D.add: object can't be added as a child of itself.",e),this):(e&&e.isObject3D?(e.removeFromParent(),e.parent=this,this.children.push(e),e.dispatchEvent(Vl),Li.child=e,this.dispatchEvent(Li),Li.child=null):console.error("THREE.Object3D.add: object not an instance of THREE.Object3D.",e),this)}remove(e){if(arguments.length>1){for(let n=0;n<arguments.length;n++)this.remove(arguments[n]);return this}const t=this.children.indexOf(e);return t!==-1&&(e.parent=null,this.children.splice(t,1),e.dispatchEvent(zd),mo.child=e,this.dispatchEvent(mo),mo.child=null),this}removeFromParent(){const e=this.parent;return e!==null&&e.remove(this),this}clear(){return this.remove(...this.children)}attach(e){return this.updateWorldMatrix(!0,!1),Dn.copy(this.matrixWorld).invert(),e.parent!==null&&(e.parent.updateWorldMatrix(!0,!1),Dn.multiply(e.parent.matrixWorld)),e.applyMatrix4(Dn),e.removeFromParent(),e.parent=this,this.children.push(e),e.updateWorldMatrix(!1,!0),e.dispatchEvent(Vl),Li.child=e,this.dispatchEvent(Li),Li.child=null,this}getObjectById(e){return this.getObjectByProperty("id",e)}getObjectByName(e){return this.getObjectByProperty("name",e)}getObjectByProperty(e,t){if(this[e]===t)return this;for(let n=0,i=this.children.length;n<i;n++){const o=this.children[n].getObjectByProperty(e,t);if(o!==void 0)return o}}getObjectsByProperty(e,t,n=[]){this[e]===t&&n.push(this);const i=this.children;for(let r=0,o=i.length;r<o;r++)i[r].getObjectsByProperty(e,t,n);return n}getWorldPosition(e){return this.updateWorldMatrix(!0,!1),e.setFromMatrixPosition(this.matrixWorld)}getWorldQuaternion(e){return this.updateWorldMatrix(!0,!1),this.matrixWorld.decompose(ps,e,Od),e}getWorldScale(e){return this.updateWorldMatrix(!0,!1),this.matrixWorld.decompose(ps,Fd,e),e}getWorldDirection(e){this.updateWorldMatrix(!0,!1);const t=this.matrixWorld.elements;return e.set(t[8],t[9],t[10]).normalize()}raycast(){}traverse(e){e(this);const t=this.children;for(let n=0,i=t.length;n<i;n++)t[n].traverse(e)}traverseVisible(e){if(this.visible===!1)return;e(this);const t=this.children;for(let n=0,i=t.length;n<i;n++)t[n].traverseVisible(e)}traverseAncestors(e){const t=this.parent;t!==null&&(e(t),t.traverseAncestors(e))}updateMatrix(){this.matrix.compose(this.position,this.quaternion,this.scale),this.matrixWorldNeedsUpdate=!0}updateMatrixWorld(e){this.matrixAutoUpdate&&this.updateMatrix(),(this.matrixWorldNeedsUpdate||e)&&(this.matrixWorldAutoUpdate===!0&&(this.parent===null?this.matrixWorld.copy(this.matrix):this.matrixWorld.multiplyMatrices(this.parent.matrixWorld,this.matrix)),this.matrixWorldNeedsUpdate=!1,e=!0);const t=this.children;for(let n=0,i=t.length;n<i;n++)t[n].updateMatrixWorld(e)}updateWorldMatrix(e,t){const n=this.parent;if(e===!0&&n!==null&&n.updateWorldMatrix(!0,!1),this.matrixAutoUpdate&&this.updateMatrix(),this.matrixWorldAutoUpdate===!0&&(this.parent===null?this.matrixWorld.copy(this.matrix):this.matrixWorld.multiplyMatrices(this.parent.matrixWorld,this.matrix)),t===!0){const i=this.children;for(let r=0,o=i.length;r<o;r++)i[r].updateWorldMatrix(!1,!0)}}toJSON(e){const t=e===void 0||typeof e=="string",n={};t&&(e={geometries:{},materials:{},textures:{},images:{},shapes:{},skeletons:{},animations:{},nodes:{}},n.metadata={version:4.6,type:"Object",generator:"Object3D.toJSON"});const i={};i.uuid=this.uuid,i.type=this.type,this.name!==""&&(i.name=this.name),this.castShadow===!0&&(i.castShadow=!0),this.receiveShadow===!0&&(i.receiveShadow=!0),this.visible===!1&&(i.visible=!1),this.frustumCulled===!1&&(i.frustumCulled=!1),this.renderOrder!==0&&(i.renderOrder=this.renderOrder),Object.keys(this.userData).length>0&&(i.userData=this.userData),i.layers=this.layers.mask,i.matrix=this.matrix.toArray(),i.up=this.up.toArray(),this.matrixAutoUpdate===!1&&(i.matrixAutoUpdate=!1),this.isInstancedMesh&&(i.type="InstancedMesh",i.count=this.count,i.instanceMatrix=this.instanceMatrix.toJSON(),this.instanceColor!==null&&(i.instanceColor=this.instanceColor.toJSON())),this.isBatchedMesh&&(i.type="BatchedMesh",i.perObjectFrustumCulled=this.perObjectFrustumCulled,i.sortObjects=this.sortObjects,i.drawRanges=this._drawRanges,i.reservedRanges=this._reservedRanges,i.visibility=this._visibility,i.active=this._active,i.bounds=this._bounds.map(a=>({boxInitialized:a.boxInitialized,boxMin:a.box.min.toArray(),boxMax:a.box.max.toArray(),sphereInitialized:a.sphereInitialized,sphereRadius:a.sphere.radius,sphereCenter:a.sphere.center.toArray()})),i.maxInstanceCount=this._maxInstanceCount,i.maxVertexCount=this._maxVertexCount,i.maxIndexCount=this._maxIndexCount,i.geometryInitialized=this._geometryInitialized,i.geometryCount=this._geometryCount,i.matricesTexture=this._matricesTexture.toJSON(e),this._colorsTexture!==null&&(i.colorsTexture=this._colorsTexture.toJSON(e)),this.boundingSphere!==null&&(i.boundingSphere={center:i.boundingSphere.center.toArray(),radius:i.boundingSphere.radius}),this.boundingBox!==null&&(i.boundingBox={min:i.boundingBox.min.toArray(),max:i.boundingBox.max.toArray()}));function r(a,l){return a[l.uuid]===void 0&&(a[l.uuid]=l.toJSON(e)),l.uuid}if(this.isScene)this.background&&(this.background.isColor?i.background=this.background.toJSON():this.background.isTexture&&(i.background=this.background.toJSON(e).uuid)),this.environment&&this.environment.isTexture&&this.environment.isRenderTargetTexture!==!0&&(i.environment=this.environment.toJSON(e).uuid);else if(this.isMesh||this.isLine||this.isPoints){i.geometry=r(e.geometries,this.geometry);const a=this.geometry.parameters;if(a!==void 0&&a.shapes!==void 0){const l=a.shapes;if(Array.isArray(l))for(let c=0,h=l.length;c<h;c++){const u=l[c];r(e.shapes,u)}else r(e.shapes,l)}}if(this.isSkinnedMesh&&(i.bindMode=this.bindMode,i.bindMatrix=this.bindMatrix.toArray(),this.skeleton!==void 0&&(r(e.skeletons,this.skeleton),i.skeleton=this.skeleton.uuid)),this.material!==void 0)if(Array.isArray(this.material)){const a=[];for(let l=0,c=this.material.length;l<c;l++)a.push(r(e.materials,this.material[l]));i.material=a}else i.material=r(e.materials,this.material);if(this.children.length>0){i.children=[];for(let a=0;a<this.children.length;a++)i.children.push(this.children[a].toJSON(e).object)}if(this.animations.length>0){i.animations=[];for(let a=0;a<this.animations.length;a++){const l=this.animations[a];i.animations.push(r(e.animations,l))}}if(t){const a=o(e.geometries),l=o(e.materials),c=o(e.textures),h=o(e.images),u=o(e.shapes),d=o(e.skeletons),f=o(e.animations),g=o(e.nodes);a.length>0&&(n.geometries=a),l.length>0&&(n.materials=l),c.length>0&&(n.textures=c),h.length>0&&(n.images=h),u.length>0&&(n.shapes=u),d.length>0&&(n.skeletons=d),f.length>0&&(n.animations=f),g.length>0&&(n.nodes=g)}return n.object=i,n;function o(a){const l=[];for(const c in a){const h=a[c];delete h.metadata,l.push(h)}return l}}clone(e){return new this.constructor().copy(this,e)}copy(e,t=!0){if(this.name=e.name,this.up.copy(e.up),this.position.copy(e.position),this.rotation.order=e.rotation.order,this.quaternion.copy(e.quaternion),this.scale.copy(e.scale),this.matrix.copy(e.matrix),this.matrixWorld.copy(e.matrixWorld),this.matrixAutoUpdate=e.matrixAutoUpdate,this.matrixWorldAutoUpdate=e.matrixWorldAutoUpdate,this.matrixWorldNeedsUpdate=e.matrixWorldNeedsUpdate,this.layers.mask=e.layers.mask,this.visible=e.visible,this.castShadow=e.castShadow,this.receiveShadow=e.receiveShadow,this.frustumCulled=e.frustumCulled,this.renderOrder=e.renderOrder,this.animations=e.animations.slice(),this.userData=JSON.parse(JSON.stringify(e.userData)),t===!0)for(let n=0;n<e.children.length;n++){const i=e.children[n];this.add(i.clone())}return this}}Mt.DEFAULT_UP=new w(0,1,0);Mt.DEFAULT_MATRIX_AUTO_UPDATE=!0;Mt.DEFAULT_MATRIX_WORLD_AUTO_UPDATE=!0;const mn=new w,In=new w,go=new w,Ln=new w,Ni=new w,Ui=new w,Hl=new w,vo=new w,xo=new w,_o=new w,yo=new ot,Mo=new ot,bo=new ot;class cn{constructor(e=new w,t=new w,n=new w){this.a=e,this.b=t,this.c=n}static getNormal(e,t,n,i){i.subVectors(n,t),mn.subVectors(e,t),i.cross(mn);const r=i.lengthSq();return r>0?i.multiplyScalar(1/Math.sqrt(r)):i.set(0,0,0)}static getBarycoord(e,t,n,i,r){mn.subVectors(i,t),In.subVectors(n,t),go.subVectors(e,t);const o=mn.dot(mn),a=mn.dot(In),l=mn.dot(go),c=In.dot(In),h=In.dot(go),u=o*c-a*a;if(u===0)return r.set(0,0,0),null;const d=1/u,f=(c*l-a*h)*d,g=(o*h-a*l)*d;return r.set(1-f-g,g,f)}static containsPoint(e,t,n,i){return this.getBarycoord(e,t,n,i,Ln)===null?!1:Ln.x>=0&&Ln.y>=0&&Ln.x+Ln.y<=1}static getInterpolation(e,t,n,i,r,o,a,l){return this.getBarycoord(e,t,n,i,Ln)===null?(l.x=0,l.y=0,"z"in l&&(l.z=0),"w"in l&&(l.w=0),null):(l.setScalar(0),l.addScaledVector(r,Ln.x),l.addScaledVector(o,Ln.y),l.addScaledVector(a,Ln.z),l)}static getInterpolatedAttribute(e,t,n,i,r,o){return yo.setScalar(0),Mo.setScalar(0),bo.setScalar(0),yo.fromBufferAttribute(e,t),Mo.fromBufferAttribute(e,n),bo.fromBufferAttribute(e,i),o.setScalar(0),o.addScaledVector(yo,r.x),o.addScaledVector(Mo,r.y),o.addScaledVector(bo,r.z),o}static isFrontFacing(e,t,n,i){return mn.subVectors(n,t),In.subVectors(e,t),mn.cross(In).dot(i)<0}set(e,t,n){return this.a.copy(e),this.b.copy(t),this.c.copy(n),this}setFromPointsAndIndices(e,t,n,i){return this.a.copy(e[t]),this.b.copy(e[n]),this.c.copy(e[i]),this}setFromAttributeAndIndices(e,t,n,i){return this.a.fromBufferAttribute(e,t),this.b.fromBufferAttribute(e,n),this.c.fromBufferAttribute(e,i),this}clone(){return new this.constructor().copy(this)}copy(e){return this.a.copy(e.a),this.b.copy(e.b),this.c.copy(e.c),this}getArea(){return mn.subVectors(this.c,this.b),In.subVectors(this.a,this.b),mn.cross(In).length()*.5}getMidpoint(e){return e.addVectors(this.a,this.b).add(this.c).multiplyScalar(1/3)}getNormal(e){return cn.getNormal(this.a,this.b,this.c,e)}getPlane(e){return e.setFromCoplanarPoints(this.a,this.b,this.c)}getBarycoord(e,t){return cn.getBarycoord(e,this.a,this.b,this.c,t)}getInterpolation(e,t,n,i,r){return cn.getInterpolation(e,this.a,this.b,this.c,t,n,i,r)}containsPoint(e){return cn.containsPoint(e,this.a,this.b,this.c)}isFrontFacing(e){return cn.isFrontFacing(this.a,this.b,this.c,e)}intersectsBox(e){return e.intersectsTriangle(this)}closestPointToPoint(e,t){const n=this.a,i=this.b,r=this.c;let o,a;Ni.subVectors(i,n),Ui.subVectors(r,n),vo.subVectors(e,n);const l=Ni.dot(vo),c=Ui.dot(vo);if(l<=0&&c<=0)return t.copy(n);xo.subVectors(e,i);const h=Ni.dot(xo),u=Ui.dot(xo);if(h>=0&&u<=h)return t.copy(i);const d=l*u-h*c;if(d<=0&&l>=0&&h<=0)return o=l/(l-h),t.copy(n).addScaledVector(Ni,o);_o.subVectors(e,r);const f=Ni.dot(_o),g=Ui.dot(_o);if(g>=0&&f<=g)return t.copy(r);const x=f*c-l*g;if(x<=0&&c>=0&&g<=0)return a=c/(c-g),t.copy(n).addScaledVector(Ui,a);const p=h*g-f*u;if(p<=0&&u-h>=0&&f-g>=0)return Hl.subVectors(r,i),a=(u-h)/(u-h+(f-g)),t.copy(i).addScaledVector(Hl,a);const m=1/(p+x+d);return o=x*m,a=d*m,t.copy(n).addScaledVector(Ni,o).addScaledVector(Ui,a)}equals(e){return e.a.equals(this.a)&&e.b.equals(this.b)&&e.c.equals(this.c)}}const Dh={aliceblue:15792383,antiquewhite:16444375,aqua:65535,aquamarine:8388564,azure:15794175,beige:16119260,bisque:16770244,black:0,blanchedalmond:16772045,blue:255,blueviolet:9055202,brown:10824234,burlywood:14596231,cadetblue:6266528,chartreuse:8388352,chocolate:13789470,coral:16744272,cornflowerblue:6591981,cornsilk:16775388,crimson:14423100,cyan:65535,darkblue:139,darkcyan:35723,darkgoldenrod:12092939,darkgray:11119017,darkgreen:25600,darkgrey:11119017,darkkhaki:12433259,darkmagenta:9109643,darkolivegreen:5597999,darkorange:16747520,darkorchid:10040012,darkred:9109504,darksalmon:15308410,darkseagreen:9419919,darkslateblue:4734347,darkslategray:3100495,darkslategrey:3100495,darkturquoise:52945,darkviolet:9699539,deeppink:16716947,deepskyblue:49151,dimgray:6908265,dimgrey:6908265,dodgerblue:2003199,firebrick:11674146,floralwhite:16775920,forestgreen:2263842,fuchsia:16711935,gainsboro:14474460,ghostwhite:16316671,gold:16766720,goldenrod:14329120,gray:8421504,green:32768,greenyellow:11403055,grey:8421504,honeydew:15794160,hotpink:16738740,indianred:13458524,indigo:4915330,ivory:16777200,khaki:15787660,lavender:15132410,lavenderblush:16773365,lawngreen:8190976,lemonchiffon:16775885,lightblue:11393254,lightcoral:15761536,lightcyan:14745599,lightgoldenrodyellow:16448210,lightgray:13882323,lightgreen:9498256,lightgrey:13882323,lightpink:16758465,lightsalmon:16752762,lightseagreen:2142890,lightskyblue:8900346,lightslategray:7833753,lightslategrey:7833753,lightsteelblue:11584734,lightyellow:16777184,lime:65280,limegreen:3329330,linen:16445670,magenta:16711935,maroon:8388608,mediumaquamarine:6737322,mediumblue:205,mediumorchid:12211667,mediumpurple:9662683,mediumseagreen:3978097,mediumslateblue:8087790,mediumspringgreen:64154,mediumturquoise:4772300,mediumvioletred:13047173,midnightblue:1644912,mintcream:16121850,mistyrose:16770273,moccasin:16770229,navajowhite:16768685,navy:128,oldlace:16643558,olive:8421376,olivedrab:7048739,orange:16753920,orangered:16729344,orchid:14315734,palegoldenrod:15657130,palegreen:10025880,paleturquoise:11529966,palevioletred:14381203,papayawhip:16773077,peachpuff:16767673,peru:13468991,pink:16761035,plum:14524637,powderblue:11591910,purple:8388736,rebeccapurple:6697881,red:16711680,rosybrown:12357519,royalblue:4286945,saddlebrown:9127187,salmon:16416882,sandybrown:16032864,seagreen:3050327,seashell:16774638,sienna:10506797,silver:12632256,skyblue:8900331,slateblue:6970061,slategray:7372944,slategrey:7372944,snow:16775930,springgreen:65407,steelblue:4620980,tan:13808780,teal:32896,thistle:14204888,tomato:16737095,turquoise:4251856,violet:15631086,wheat:16113331,white:16777215,whitesmoke:16119285,yellow:16776960,yellowgreen:10145074},jn={h:0,s:0,l:0},Zs={h:0,s:0,l:0};function wo(s,e,t){return t<0&&(t+=1),t>1&&(t-=1),t<1/6?s+(e-s)*6*t:t<1/2?e:t<2/3?s+(e-s)*6*(2/3-t):s}class Ne{constructor(e,t,n){return this.isColor=!0,this.r=1,this.g=1,this.b=1,this.set(e,t,n)}set(e,t,n){if(t===void 0&&n===void 0){const i=e;i&&i.isColor?this.copy(i):typeof i=="number"?this.setHex(i):typeof i=="string"&&this.setStyle(i)}else this.setRGB(e,t,n);return this}setScalar(e){return this.r=e,this.g=e,this.b=e,this}setHex(e,t=Ft){return e=Math.floor(e),this.r=(e>>16&255)/255,this.g=(e>>8&255)/255,this.b=(e&255)/255,nt.toWorkingColorSpace(this,t),this}setRGB(e,t,n,i=nt.workingColorSpace){return this.r=e,this.g=t,this.b=n,nt.toWorkingColorSpace(this,i),this}setHSL(e,t,n,i=nt.workingColorSpace){if(e=$a(e,1),t=Tt(t,0,1),n=Tt(n,0,1),t===0)this.r=this.g=this.b=n;else{const r=n<=.5?n*(1+t):n+t-n*t,o=2*n-r;this.r=wo(o,r,e+1/3),this.g=wo(o,r,e),this.b=wo(o,r,e-1/3)}return nt.toWorkingColorSpace(this,i),this}setStyle(e,t=Ft){function n(r){r!==void 0&&parseFloat(r)<1&&console.warn("THREE.Color: Alpha component of "+e+" will be ignored.")}let i;if(i=/^(\w+)\(([^\)]*)\)/.exec(e)){let r;const o=i[1],a=i[2];switch(o){case"rgb":case"rgba":if(r=/^\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*(\d*\.?\d+)\s*)?$/.exec(a))return n(r[4]),this.setRGB(Math.min(255,parseInt(r[1],10))/255,Math.min(255,parseInt(r[2],10))/255,Math.min(255,parseInt(r[3],10))/255,t);if(r=/^\s*(\d+)\%\s*,\s*(\d+)\%\s*,\s*(\d+)\%\s*(?:,\s*(\d*\.?\d+)\s*)?$/.exec(a))return n(r[4]),this.setRGB(Math.min(100,parseInt(r[1],10))/100,Math.min(100,parseInt(r[2],10))/100,Math.min(100,parseInt(r[3],10))/100,t);break;case"hsl":case"hsla":if(r=/^\s*(\d*\.?\d+)\s*,\s*(\d*\.?\d+)\%\s*,\s*(\d*\.?\d+)\%\s*(?:,\s*(\d*\.?\d+)\s*)?$/.exec(a))return n(r[4]),this.setHSL(parseFloat(r[1])/360,parseFloat(r[2])/100,parseFloat(r[3])/100,t);break;default:console.warn("THREE.Color: Unknown color model "+e)}}else if(i=/^\#([A-Fa-f\d]+)$/.exec(e)){const r=i[1],o=r.length;if(o===3)return this.setRGB(parseInt(r.charAt(0),16)/15,parseInt(r.charAt(1),16)/15,parseInt(r.charAt(2),16)/15,t);if(o===6)return this.setHex(parseInt(r,16),t);console.warn("THREE.Color: Invalid hex color "+e)}else if(e&&e.length>0)return this.setColorName(e,t);return this}setColorName(e,t=Ft){const n=Dh[e.toLowerCase()];return n!==void 0?this.setHex(n,t):console.warn("THREE.Color: Unknown color "+e),this}clone(){return new this.constructor(this.r,this.g,this.b)}copy(e){return this.r=e.r,this.g=e.g,this.b=e.b,this}copySRGBToLinear(e){return this.r=Ki(e.r),this.g=Ki(e.g),this.b=Ki(e.b),this}copyLinearToSRGB(e){return this.r=oo(e.r),this.g=oo(e.g),this.b=oo(e.b),this}convertSRGBToLinear(){return this.copySRGBToLinear(this),this}convertLinearToSRGB(){return this.copyLinearToSRGB(this),this}getHex(e=Ft){return nt.fromWorkingColorSpace(Vt.copy(this),e),Math.round(Tt(Vt.r*255,0,255))*65536+Math.round(Tt(Vt.g*255,0,255))*256+Math.round(Tt(Vt.b*255,0,255))}getHexString(e=Ft){return("000000"+this.getHex(e).toString(16)).slice(-6)}getHSL(e,t=nt.workingColorSpace){nt.fromWorkingColorSpace(Vt.copy(this),t);const n=Vt.r,i=Vt.g,r=Vt.b,o=Math.max(n,i,r),a=Math.min(n,i,r);let l,c;const h=(a+o)/2;if(a===o)l=0,c=0;else{const u=o-a;switch(c=h<=.5?u/(o+a):u/(2-o-a),o){case n:l=(i-r)/u+(i<r?6:0);break;case i:l=(r-n)/u+2;break;case r:l=(n-i)/u+4;break}l/=6}return e.h=l,e.s=c,e.l=h,e}getRGB(e,t=nt.workingColorSpace){return nt.fromWorkingColorSpace(Vt.copy(this),t),e.r=Vt.r,e.g=Vt.g,e.b=Vt.b,e}getStyle(e=Ft){nt.fromWorkingColorSpace(Vt.copy(this),e);const t=Vt.r,n=Vt.g,i=Vt.b;return e!==Ft?`color(${e} ${t.toFixed(3)} ${n.toFixed(3)} ${i.toFixed(3)})`:`rgb(${Math.round(t*255)},${Math.round(n*255)},${Math.round(i*255)})`}offsetHSL(e,t,n){return this.getHSL(jn),this.setHSL(jn.h+e,jn.s+t,jn.l+n)}add(e){return this.r+=e.r,this.g+=e.g,this.b+=e.b,this}addColors(e,t){return this.r=e.r+t.r,this.g=e.g+t.g,this.b=e.b+t.b,this}addScalar(e){return this.r+=e,this.g+=e,this.b+=e,this}sub(e){return this.r=Math.max(0,this.r-e.r),this.g=Math.max(0,this.g-e.g),this.b=Math.max(0,this.b-e.b),this}multiply(e){return this.r*=e.r,this.g*=e.g,this.b*=e.b,this}multiplyScalar(e){return this.r*=e,this.g*=e,this.b*=e,this}lerp(e,t){return this.r+=(e.r-this.r)*t,this.g+=(e.g-this.g)*t,this.b+=(e.b-this.b)*t,this}lerpColors(e,t,n){return this.r=e.r+(t.r-e.r)*n,this.g=e.g+(t.g-e.g)*n,this.b=e.b+(t.b-e.b)*n,this}lerpHSL(e,t){this.getHSL(jn),e.getHSL(Zs);const n=Ts(jn.h,Zs.h,t),i=Ts(jn.s,Zs.s,t),r=Ts(jn.l,Zs.l,t);return this.setHSL(n,i,r),this}setFromVector3(e){return this.r=e.x,this.g=e.y,this.b=e.z,this}applyMatrix3(e){const t=this.r,n=this.g,i=this.b,r=e.elements;return this.r=r[0]*t+r[3]*n+r[6]*i,this.g=r[1]*t+r[4]*n+r[7]*i,this.b=r[2]*t+r[5]*n+r[8]*i,this}equals(e){return e.r===this.r&&e.g===this.g&&e.b===this.b}fromArray(e,t=0){return this.r=e[t],this.g=e[t+1],this.b=e[t+2],this}toArray(e=[],t=0){return e[t]=this.r,e[t+1]=this.g,e[t+2]=this.b,e}fromBufferAttribute(e,t){return this.r=e.getX(t),this.g=e.getY(t),this.b=e.getZ(t),this}toJSON(){return this.getHex()}*[Symbol.iterator](){yield this.r,yield this.g,yield this.b}}const Vt=new Ne;Ne.NAMES=Dh;let kd=0;class wi extends _i{constructor(){super(),this.isMaterial=!0,Object.defineProperty(this,"id",{value:kd++}),this.uuid=yi(),this.name="",this.type="Material",this.blending=Qn,this.side=wn,this.vertexColors=!1,this.opacity=1,this.transparent=!1,this.alphaHash=!1,this.blendSrc=Yo,this.blendDst=qo,this.blendEquation=ui,this.blendSrcAlpha=null,this.blendDstAlpha=null,this.blendEquationAlpha=null,this.blendColor=new Ne(0,0,0),this.blendAlpha=0,this.depthFunc=Ji,this.depthTest=!0,this.depthWrite=!0,this.stencilWriteMask=255,this.stencilFunc=Al,this.stencilRef=0,this.stencilFuncMask=255,this.stencilFail=Ei,this.stencilZFail=Ei,this.stencilZPass=Ei,this.stencilWrite=!1,this.clippingPlanes=null,this.clipIntersection=!1,this.clipShadows=!1,this.shadowSide=null,this.colorWrite=!0,this.precision=null,this.polygonOffset=!1,this.polygonOffsetFactor=0,this.polygonOffsetUnits=0,this.dithering=!1,this.alphaToCoverage=!1,this.premultipliedAlpha=!1,this.forceSinglePass=!1,this.visible=!0,this.toneMapped=!0,this.userData={},this.version=0,this._alphaTest=0}get alphaTest(){return this._alphaTest}set alphaTest(e){this._alphaTest>0!=e>0&&this.version++,this._alphaTest=e}onBeforeRender(){}onBeforeCompile(){}customProgramCacheKey(){return this.onBeforeCompile.toString()}setValues(e){if(e!==void 0)for(const t in e){const n=e[t];if(n===void 0){console.warn(`THREE.Material: parameter '${t}' has value of undefined.`);continue}const i=this[t];if(i===void 0){console.warn(`THREE.Material: '${t}' is not a property of THREE.${this.type}.`);continue}i&&i.isColor?i.set(n):i&&i.isVector3&&n&&n.isVector3?i.copy(n):this[t]=n}}toJSON(e){const t=e===void 0||typeof e=="string";t&&(e={textures:{},images:{}});const n={metadata:{version:4.6,type:"Material",generator:"Material.toJSON"}};n.uuid=this.uuid,n.type=this.type,this.name!==""&&(n.name=this.name),this.color&&this.color.isColor&&(n.color=this.color.getHex()),this.roughness!==void 0&&(n.roughness=this.roughness),this.metalness!==void 0&&(n.metalness=this.metalness),this.sheen!==void 0&&(n.sheen=this.sheen),this.sheenColor&&this.sheenColor.isColor&&(n.sheenColor=this.sheenColor.getHex()),this.sheenRoughness!==void 0&&(n.sheenRoughness=this.sheenRoughness),this.emissive&&this.emissive.isColor&&(n.emissive=this.emissive.getHex()),this.emissiveIntensity!==void 0&&this.emissiveIntensity!==1&&(n.emissiveIntensity=this.emissiveIntensity),this.specular&&this.specular.isColor&&(n.specular=this.specular.getHex()),this.specularIntensity!==void 0&&(n.specularIntensity=this.specularIntensity),this.specularColor&&this.specularColor.isColor&&(n.specularColor=this.specularColor.getHex()),this.shininess!==void 0&&(n.shininess=this.shininess),this.clearcoat!==void 0&&(n.clearcoat=this.clearcoat),this.clearcoatRoughness!==void 0&&(n.clearcoatRoughness=this.clearcoatRoughness),this.clearcoatMap&&this.clearcoatMap.isTexture&&(n.clearcoatMap=this.clearcoatMap.toJSON(e).uuid),this.clearcoatRoughnessMap&&this.clearcoatRoughnessMap.isTexture&&(n.clearcoatRoughnessMap=this.clearcoatRoughnessMap.toJSON(e).uuid),this.clearcoatNormalMap&&this.clearcoatNormalMap.isTexture&&(n.clearcoatNormalMap=this.clearcoatNormalMap.toJSON(e).uuid,n.clearcoatNormalScale=this.clearcoatNormalScale.toArray()),this.dispersion!==void 0&&(n.dispersion=this.dispersion),this.iridescence!==void 0&&(n.iridescence=this.iridescence),this.iridescenceIOR!==void 0&&(n.iridescenceIOR=this.iridescenceIOR),this.iridescenceThicknessRange!==void 0&&(n.iridescenceThicknessRange=this.iridescenceThicknessRange),this.iridescenceMap&&this.iridescenceMap.isTexture&&(n.iridescenceMap=this.iridescenceMap.toJSON(e).uuid),this.iridescenceThicknessMap&&this.iridescenceThicknessMap.isTexture&&(n.iridescenceThicknessMap=this.iridescenceThicknessMap.toJSON(e).uuid),this.anisotropy!==void 0&&(n.anisotropy=this.anisotropy),this.anisotropyRotation!==void 0&&(n.anisotropyRotation=this.anisotropyRotation),this.anisotropyMap&&this.anisotropyMap.isTexture&&(n.anisotropyMap=this.anisotropyMap.toJSON(e).uuid),this.map&&this.map.isTexture&&(n.map=this.map.toJSON(e).uuid),this.matcap&&this.matcap.isTexture&&(n.matcap=this.matcap.toJSON(e).uuid),this.alphaMap&&this.alphaMap.isTexture&&(n.alphaMap=this.alphaMap.toJSON(e).uuid),this.lightMap&&this.lightMap.isTexture&&(n.lightMap=this.lightMap.toJSON(e).uuid,n.lightMapIntensity=this.lightMapIntensity),this.aoMap&&this.aoMap.isTexture&&(n.aoMap=this.aoMap.toJSON(e).uuid,n.aoMapIntensity=this.aoMapIntensity),this.bumpMap&&this.bumpMap.isTexture&&(n.bumpMap=this.bumpMap.toJSON(e).uuid,n.bumpScale=this.bumpScale),this.normalMap&&this.normalMap.isTexture&&(n.normalMap=this.normalMap.toJSON(e).uuid,n.normalMapType=this.normalMapType,n.normalScale=this.normalScale.toArray()),this.displacementMap&&this.displacementMap.isTexture&&(n.displacementMap=this.displacementMap.toJSON(e).uuid,n.displacementScale=this.displacementScale,n.displacementBias=this.displacementBias),this.roughnessMap&&this.roughnessMap.isTexture&&(n.roughnessMap=this.roughnessMap.toJSON(e).uuid),this.metalnessMap&&this.metalnessMap.isTexture&&(n.metalnessMap=this.metalnessMap.toJSON(e).uuid),this.emissiveMap&&this.emissiveMap.isTexture&&(n.emissiveMap=this.emissiveMap.toJSON(e).uuid),this.specularMap&&this.specularMap.isTexture&&(n.specularMap=this.specularMap.toJSON(e).uuid),this.specularIntensityMap&&this.specularIntensityMap.isTexture&&(n.specularIntensityMap=this.specularIntensityMap.toJSON(e).uuid),this.specularColorMap&&this.specularColorMap.isTexture&&(n.specularColorMap=this.specularColorMap.toJSON(e).uuid),this.envMap&&this.envMap.isTexture&&(n.envMap=this.envMap.toJSON(e).uuid,this.combine!==void 0&&(n.combine=this.combine)),this.envMapRotation!==void 0&&(n.envMapRotation=this.envMapRotation.toArray()),this.envMapIntensity!==void 0&&(n.envMapIntensity=this.envMapIntensity),this.reflectivity!==void 0&&(n.reflectivity=this.reflectivity),this.refractionRatio!==void 0&&(n.refractionRatio=this.refractionRatio),this.gradientMap&&this.gradientMap.isTexture&&(n.gradientMap=this.gradientMap.toJSON(e).uuid),this.transmission!==void 0&&(n.transmission=this.transmission),this.transmissionMap&&this.transmissionMap.isTexture&&(n.transmissionMap=this.transmissionMap.toJSON(e).uuid),this.thickness!==void 0&&(n.thickness=this.thickness),this.thicknessMap&&this.thicknessMap.isTexture&&(n.thicknessMap=this.thicknessMap.toJSON(e).uuid),this.attenuationDistance!==void 0&&this.attenuationDistance!==1/0&&(n.attenuationDistance=this.attenuationDistance),this.attenuationColor!==void 0&&(n.attenuationColor=this.attenuationColor.getHex()),this.size!==void 0&&(n.size=this.size),this.shadowSide!==null&&(n.shadowSide=this.shadowSide),this.sizeAttenuation!==void 0&&(n.sizeAttenuation=this.sizeAttenuation),this.blending!==Qn&&(n.blending=this.blending),this.side!==wn&&(n.side=this.side),this.vertexColors===!0&&(n.vertexColors=!0),this.opacity<1&&(n.opacity=this.opacity),this.transparent===!0&&(n.transparent=!0),this.blendSrc!==Yo&&(n.blendSrc=this.blendSrc),this.blendDst!==qo&&(n.blendDst=this.blendDst),this.blendEquation!==ui&&(n.blendEquation=this.blendEquation),this.blendSrcAlpha!==null&&(n.blendSrcAlpha=this.blendSrcAlpha),this.blendDstAlpha!==null&&(n.blendDstAlpha=this.blendDstAlpha),this.blendEquationAlpha!==null&&(n.blendEquationAlpha=this.blendEquationAlpha),this.blendColor&&this.blendColor.isColor&&(n.blendColor=this.blendColor.getHex()),this.blendAlpha!==0&&(n.blendAlpha=this.blendAlpha),this.depthFunc!==Ji&&(n.depthFunc=this.depthFunc),this.depthTest===!1&&(n.depthTest=this.depthTest),this.depthWrite===!1&&(n.depthWrite=this.depthWrite),this.colorWrite===!1&&(n.colorWrite=this.colorWrite),this.stencilWriteMask!==255&&(n.stencilWriteMask=this.stencilWriteMask),this.stencilFunc!==Al&&(n.stencilFunc=this.stencilFunc),this.stencilRef!==0&&(n.stencilRef=this.stencilRef),this.stencilFuncMask!==255&&(n.stencilFuncMask=this.stencilFuncMask),this.stencilFail!==Ei&&(n.stencilFail=this.stencilFail),this.stencilZFail!==Ei&&(n.stencilZFail=this.stencilZFail),this.stencilZPass!==Ei&&(n.stencilZPass=this.stencilZPass),this.stencilWrite===!0&&(n.stencilWrite=this.stencilWrite),this.rotation!==void 0&&this.rotation!==0&&(n.rotation=this.rotation),this.polygonOffset===!0&&(n.polygonOffset=!0),this.polygonOffsetFactor!==0&&(n.polygonOffsetFactor=this.polygonOffsetFactor),this.polygonOffsetUnits!==0&&(n.polygonOffsetUnits=this.polygonOffsetUnits),this.linewidth!==void 0&&this.linewidth!==1&&(n.linewidth=this.linewidth),this.dashSize!==void 0&&(n.dashSize=this.dashSize),this.gapSize!==void 0&&(n.gapSize=this.gapSize),this.scale!==void 0&&(n.scale=this.scale),this.dithering===!0&&(n.dithering=!0),this.alphaTest>0&&(n.alphaTest=this.alphaTest),this.alphaHash===!0&&(n.alphaHash=!0),this.alphaToCoverage===!0&&(n.alphaToCoverage=!0),this.premultipliedAlpha===!0&&(n.premultipliedAlpha=!0),this.forceSinglePass===!0&&(n.forceSinglePass=!0),this.wireframe===!0&&(n.wireframe=!0),this.wireframeLinewidth>1&&(n.wireframeLinewidth=this.wireframeLinewidth),this.wireframeLinecap!=="round"&&(n.wireframeLinecap=this.wireframeLinecap),this.wireframeLinejoin!=="round"&&(n.wireframeLinejoin=this.wireframeLinejoin),this.flatShading===!0&&(n.flatShading=!0),this.visible===!1&&(n.visible=!1),this.toneMapped===!1&&(n.toneMapped=!1),this.fog===!1&&(n.fog=!1),Object.keys(this.userData).length>0&&(n.userData=this.userData);function i(r){const o=[];for(const a in r){const l=r[a];delete l.metadata,o.push(l)}return o}if(t){const r=i(e.textures),o=i(e.images);r.length>0&&(n.textures=r),o.length>0&&(n.images=o)}return n}clone(){return new this.constructor().copy(this)}copy(e){this.name=e.name,this.blending=e.blending,this.side=e.side,this.vertexColors=e.vertexColors,this.opacity=e.opacity,this.transparent=e.transparent,this.blendSrc=e.blendSrc,this.blendDst=e.blendDst,this.blendEquation=e.blendEquation,this.blendSrcAlpha=e.blendSrcAlpha,this.blendDstAlpha=e.blendDstAlpha,this.blendEquationAlpha=e.blendEquationAlpha,this.blendColor.copy(e.blendColor),this.blendAlpha=e.blendAlpha,this.depthFunc=e.depthFunc,this.depthTest=e.depthTest,this.depthWrite=e.depthWrite,this.stencilWriteMask=e.stencilWriteMask,this.stencilFunc=e.stencilFunc,this.stencilRef=e.stencilRef,this.stencilFuncMask=e.stencilFuncMask,this.stencilFail=e.stencilFail,this.stencilZFail=e.stencilZFail,this.stencilZPass=e.stencilZPass,this.stencilWrite=e.stencilWrite;const t=e.clippingPlanes;let n=null;if(t!==null){const i=t.length;n=new Array(i);for(let r=0;r!==i;++r)n[r]=t[r].clone()}return this.clippingPlanes=n,this.clipIntersection=e.clipIntersection,this.clipShadows=e.clipShadows,this.shadowSide=e.shadowSide,this.colorWrite=e.colorWrite,this.precision=e.precision,this.polygonOffset=e.polygonOffset,this.polygonOffsetFactor=e.polygonOffsetFactor,this.polygonOffsetUnits=e.polygonOffsetUnits,this.dithering=e.dithering,this.alphaTest=e.alphaTest,this.alphaHash=e.alphaHash,this.alphaToCoverage=e.alphaToCoverage,this.premultipliedAlpha=e.premultipliedAlpha,this.forceSinglePass=e.forceSinglePass,this.visible=e.visible,this.toneMapped=e.toneMapped,this.userData=JSON.parse(JSON.stringify(e.userData)),this}dispose(){this.dispatchEvent({type:"dispose"})}set needsUpdate(e){e===!0&&this.version++}onBuild(){console.warn("Material: onBuild() has been removed.")}}class Ge extends wi{constructor(e){super(),this.isMeshBasicMaterial=!0,this.type="MeshBasicMaterial",this.color=new Ne(16777215),this.map=null,this.lightMap=null,this.lightMapIntensity=1,this.aoMap=null,this.aoMapIntensity=1,this.specularMap=null,this.alphaMap=null,this.envMap=null,this.envMapRotation=new Yt,this.combine=hh,this.reflectivity=1,this.refractionRatio=.98,this.wireframe=!1,this.wireframeLinewidth=1,this.wireframeLinecap="round",this.wireframeLinejoin="round",this.fog=!0,this.setValues(e)}copy(e){return super.copy(e),this.color.copy(e.color),this.map=e.map,this.lightMap=e.lightMap,this.lightMapIntensity=e.lightMapIntensity,this.aoMap=e.aoMap,this.aoMapIntensity=e.aoMapIntensity,this.specularMap=e.specularMap,this.alphaMap=e.alphaMap,this.envMap=e.envMap,this.envMapRotation.copy(e.envMapRotation),this.combine=e.combine,this.reflectivity=e.reflectivity,this.refractionRatio=e.refractionRatio,this.wireframe=e.wireframe,this.wireframeLinewidth=e.wireframeLinewidth,this.wireframeLinecap=e.wireframeLinecap,this.wireframeLinejoin=e.wireframeLinejoin,this.fog=e.fog,this}}const Fn=Bd();function Bd(){const s=new ArrayBuffer(4),e=new Float32Array(s),t=new Uint32Array(s),n=new Uint32Array(512),i=new Uint32Array(512);for(let l=0;l<256;++l){const c=l-127;c<-27?(n[l]=0,n[l|256]=32768,i[l]=24,i[l|256]=24):c<-14?(n[l]=1024>>-c-14,n[l|256]=1024>>-c-14|32768,i[l]=-c-1,i[l|256]=-c-1):c<=15?(n[l]=c+15<<10,n[l|256]=c+15<<10|32768,i[l]=13,i[l|256]=13):c<128?(n[l]=31744,n[l|256]=64512,i[l]=24,i[l|256]=24):(n[l]=31744,n[l|256]=64512,i[l]=13,i[l|256]=13)}const r=new Uint32Array(2048),o=new Uint32Array(64),a=new Uint32Array(64);for(let l=1;l<1024;++l){let c=l<<13,h=0;for(;!(c&8388608);)c<<=1,h-=8388608;c&=-8388609,h+=947912704,r[l]=c|h}for(let l=1024;l<2048;++l)r[l]=939524096+(l-1024<<13);for(let l=1;l<31;++l)o[l]=l<<23;o[31]=1199570944,o[32]=2147483648;for(let l=33;l<63;++l)o[l]=2147483648+(l-32<<23);o[63]=3347054592;for(let l=1;l<64;++l)l!==32&&(a[l]=1024);return{floatView:e,uint32View:t,baseTable:n,shiftTable:i,mantissaTable:r,exponentTable:o,offsetTable:a}}function Vd(s){Math.abs(s)>65504&&console.warn("THREE.DataUtils.toHalfFloat(): Value out of range."),s=Tt(s,-65504,65504),Fn.floatView[0]=s;const e=Fn.uint32View[0],t=e>>23&511;return Fn.baseTable[t]+((e&8388607)>>Fn.shiftTable[t])}function Hd(s){const e=s>>10;return Fn.uint32View[0]=Fn.mantissaTable[Fn.offsetTable[e]+(s&1023)]+Fn.exponentTable[e],Fn.floatView[0]}const Js={toHalfFloat:Vd,fromHalfFloat:Hd},At=new w,$s=new Q;class kt{constructor(e,t,n=!1){if(Array.isArray(e))throw new TypeError("THREE.BufferAttribute: array should be a Typed Array.");this.isBufferAttribute=!0,this.name="",this.array=e,this.itemSize=t,this.count=e!==void 0?e.length/t:0,this.normalized=n,this.usage=Cl,this.updateRanges=[],this.gpuType=Tn,this.version=0}onUploadCallback(){}set needsUpdate(e){e===!0&&this.version++}setUsage(e){return this.usage=e,this}addUpdateRange(e,t){this.updateRanges.push({start:e,count:t})}clearUpdateRanges(){this.updateRanges.length=0}copy(e){return this.name=e.name,this.array=new e.array.constructor(e.array),this.itemSize=e.itemSize,this.count=e.count,this.normalized=e.normalized,this.usage=e.usage,this.gpuType=e.gpuType,this}copyAt(e,t,n){e*=this.itemSize,n*=t.itemSize;for(let i=0,r=this.itemSize;i<r;i++)this.array[e+i]=t.array[n+i];return this}copyArray(e){return this.array.set(e),this}applyMatrix3(e){if(this.itemSize===2)for(let t=0,n=this.count;t<n;t++)$s.fromBufferAttribute(this,t),$s.applyMatrix3(e),this.setXY(t,$s.x,$s.y);else if(this.itemSize===3)for(let t=0,n=this.count;t<n;t++)At.fromBufferAttribute(this,t),At.applyMatrix3(e),this.setXYZ(t,At.x,At.y,At.z);return this}applyMatrix4(e){for(let t=0,n=this.count;t<n;t++)At.fromBufferAttribute(this,t),At.applyMatrix4(e),this.setXYZ(t,At.x,At.y,At.z);return this}applyNormalMatrix(e){for(let t=0,n=this.count;t<n;t++)At.fromBufferAttribute(this,t),At.applyNormalMatrix(e),this.setXYZ(t,At.x,At.y,At.z);return this}transformDirection(e){for(let t=0,n=this.count;t<n;t++)At.fromBufferAttribute(this,t),At.transformDirection(e),this.setXYZ(t,At.x,At.y,At.z);return this}set(e,t=0){return this.array.set(e,t),this}getComponent(e,t){let n=this.array[e*this.itemSize+t];return this.normalized&&(n=Gi(n,this.array)),n}setComponent(e,t,n){return this.normalized&&(n=Wt(n,this.array)),this.array[e*this.itemSize+t]=n,this}getX(e){let t=this.array[e*this.itemSize];return this.normalized&&(t=Gi(t,this.array)),t}setX(e,t){return this.normalized&&(t=Wt(t,this.array)),this.array[e*this.itemSize]=t,this}getY(e){let t=this.array[e*this.itemSize+1];return this.normalized&&(t=Gi(t,this.array)),t}setY(e,t){return this.normalized&&(t=Wt(t,this.array)),this.array[e*this.itemSize+1]=t,this}getZ(e){let t=this.array[e*this.itemSize+2];return this.normalized&&(t=Gi(t,this.array)),t}setZ(e,t){return this.normalized&&(t=Wt(t,this.array)),this.array[e*this.itemSize+2]=t,this}getW(e){let t=this.array[e*this.itemSize+3];return this.normalized&&(t=Gi(t,this.array)),t}setW(e,t){return this.normalized&&(t=Wt(t,this.array)),this.array[e*this.itemSize+3]=t,this}setXY(e,t,n){return e*=this.itemSize,this.normalized&&(t=Wt(t,this.array),n=Wt(n,this.array)),this.array[e+0]=t,this.array[e+1]=n,this}setXYZ(e,t,n,i){return e*=this.itemSize,this.normalized&&(t=Wt(t,this.array),n=Wt(n,this.array),i=Wt(i,this.array)),this.array[e+0]=t,this.array[e+1]=n,this.array[e+2]=i,this}setXYZW(e,t,n,i,r){return e*=this.itemSize,this.normalized&&(t=Wt(t,this.array),n=Wt(n,this.array),i=Wt(i,this.array),r=Wt(r,this.array)),this.array[e+0]=t,this.array[e+1]=n,this.array[e+2]=i,this.array[e+3]=r,this}onUpload(e){return this.onUploadCallback=e,this}clone(){return new this.constructor(this.array,this.itemSize).copy(this)}toJSON(){const e={itemSize:this.itemSize,type:this.array.constructor.name,array:Array.from(this.array),normalized:this.normalized};return this.name!==""&&(e.name=this.name),this.usage!==Cl&&(e.usage=this.usage),e}}class Ih extends kt{constructor(e,t,n){super(new Uint16Array(e),t,n)}}class Lh extends kt{constructor(e,t,n){super(new Uint32Array(e),t,n)}}class Ae extends kt{constructor(e,t,n){super(new Float32Array(e),t,n)}}let Gd=0;const on=new Fe,So=new Mt,Oi=new w,nn=new Lt,ms=new Lt,Ot=new w;class je extends _i{constructor(){super(),this.isBufferGeometry=!0,Object.defineProperty(this,"id",{value:Gd++}),this.uuid=yi(),this.name="",this.type="BufferGeometry",this.index=null,this.attributes={},this.morphAttributes={},this.morphTargetsRelative=!1,this.groups=[],this.boundingBox=null,this.boundingSphere=null,this.drawRange={start:0,count:1/0},this.userData={}}getIndex(){return this.index}setIndex(e){return Array.isArray(e)?this.index=new(Ch(e)?Lh:Ih)(e,1):this.index=e,this}getAttribute(e){return this.attributes[e]}setAttribute(e,t){return this.attributes[e]=t,this}deleteAttribute(e){return delete this.attributes[e],this}hasAttribute(e){return this.attributes[e]!==void 0}addGroup(e,t,n=0){this.groups.push({start:e,count:t,materialIndex:n})}clearGroups(){this.groups=[]}setDrawRange(e,t){this.drawRange.start=e,this.drawRange.count=t}applyMatrix4(e){const t=this.attributes.position;t!==void 0&&(t.applyMatrix4(e),t.needsUpdate=!0);const n=this.attributes.normal;if(n!==void 0){const r=new Ye().getNormalMatrix(e);n.applyNormalMatrix(r),n.needsUpdate=!0}const i=this.attributes.tangent;return i!==void 0&&(i.transformDirection(e),i.needsUpdate=!0),this.boundingBox!==null&&this.computeBoundingBox(),this.boundingSphere!==null&&this.computeBoundingSphere(),this}applyQuaternion(e){return on.makeRotationFromQuaternion(e),this.applyMatrix4(on),this}rotateX(e){return on.makeRotationX(e),this.applyMatrix4(on),this}rotateY(e){return on.makeRotationY(e),this.applyMatrix4(on),this}rotateZ(e){return on.makeRotationZ(e),this.applyMatrix4(on),this}translate(e,t,n){return on.makeTranslation(e,t,n),this.applyMatrix4(on),this}scale(e,t,n){return on.makeScale(e,t,n),this.applyMatrix4(on),this}lookAt(e){return So.lookAt(e),So.updateMatrix(),this.applyMatrix4(So.matrix),this}center(){return this.computeBoundingBox(),this.boundingBox.getCenter(Oi).negate(),this.translate(Oi.x,Oi.y,Oi.z),this}setFromPoints(e){const t=[];for(let n=0,i=e.length;n<i;n++){const r=e[n];t.push(r.x,r.y,r.z||0)}return this.setAttribute("position",new Ae(t,3)),this}computeBoundingBox(){this.boundingBox===null&&(this.boundingBox=new Lt);const e=this.attributes.position,t=this.morphAttributes.position;if(e&&e.isGLBufferAttribute){console.error("THREE.BufferGeometry.computeBoundingBox(): GLBufferAttribute requires a manual bounding box.",this),this.boundingBox.set(new w(-1/0,-1/0,-1/0),new w(1/0,1/0,1/0));return}if(e!==void 0){if(this.boundingBox.setFromBufferAttribute(e),t)for(let n=0,i=t.length;n<i;n++){const r=t[n];nn.setFromBufferAttribute(r),this.morphTargetsRelative?(Ot.addVectors(this.boundingBox.min,nn.min),this.boundingBox.expandByPoint(Ot),Ot.addVectors(this.boundingBox.max,nn.max),this.boundingBox.expandByPoint(Ot)):(this.boundingBox.expandByPoint(nn.min),this.boundingBox.expandByPoint(nn.max))}}else this.boundingBox.makeEmpty();(isNaN(this.boundingBox.min.x)||isNaN(this.boundingBox.min.y)||isNaN(this.boundingBox.min.z))&&console.error('THREE.BufferGeometry.computeBoundingBox(): Computed min/max have NaN values. The "position" attribute is likely to have NaN values.',this)}computeBoundingSphere(){this.boundingSphere===null&&(this.boundingSphere=new Mi);const e=this.attributes.position,t=this.morphAttributes.position;if(e&&e.isGLBufferAttribute){console.error("THREE.BufferGeometry.computeBoundingSphere(): GLBufferAttribute requires a manual bounding sphere.",this),this.boundingSphere.set(new w,1/0);return}if(e){const n=this.boundingSphere.center;if(nn.setFromBufferAttribute(e),t)for(let r=0,o=t.length;r<o;r++){const a=t[r];ms.setFromBufferAttribute(a),this.morphTargetsRelative?(Ot.addVectors(nn.min,ms.min),nn.expandByPoint(Ot),Ot.addVectors(nn.max,ms.max),nn.expandByPoint(Ot)):(nn.expandByPoint(ms.min),nn.expandByPoint(ms.max))}nn.getCenter(n);let i=0;for(let r=0,o=e.count;r<o;r++)Ot.fromBufferAttribute(e,r),i=Math.max(i,n.distanceToSquared(Ot));if(t)for(let r=0,o=t.length;r<o;r++){const a=t[r],l=this.morphTargetsRelative;for(let c=0,h=a.count;c<h;c++)Ot.fromBufferAttribute(a,c),l&&(Oi.fromBufferAttribute(e,c),Ot.add(Oi)),i=Math.max(i,n.distanceToSquared(Ot))}this.boundingSphere.radius=Math.sqrt(i),isNaN(this.boundingSphere.radius)&&console.error('THREE.BufferGeometry.computeBoundingSphere(): Computed radius is NaN. The "position" attribute is likely to have NaN values.',this)}}computeTangents(){const e=this.index,t=this.attributes;if(e===null||t.position===void 0||t.normal===void 0||t.uv===void 0){console.error("THREE.BufferGeometry: .computeTangents() failed. Missing required attributes (index, position, normal or uv)");return}const n=t.position,i=t.normal,r=t.uv;this.hasAttribute("tangent")===!1&&this.setAttribute("tangent",new kt(new Float32Array(4*n.count),4));const o=this.getAttribute("tangent"),a=[],l=[];for(let z=0;z<n.count;z++)a[z]=new w,l[z]=new w;const c=new w,h=new w,u=new w,d=new Q,f=new Q,g=new Q,x=new w,p=new w;function m(z,T,y){c.fromBufferAttribute(n,z),h.fromBufferAttribute(n,T),u.fromBufferAttribute(n,y),d.fromBufferAttribute(r,z),f.fromBufferAttribute(r,T),g.fromBufferAttribute(r,y),h.sub(c),u.sub(c),f.sub(d),g.sub(d);const b=1/(f.x*g.y-g.x*f.y);isFinite(b)&&(x.copy(h).multiplyScalar(g.y).addScaledVector(u,-f.y).multiplyScalar(b),p.copy(u).multiplyScalar(f.x).addScaledVector(h,-g.x).multiplyScalar(b),a[z].add(x),a[T].add(x),a[y].add(x),l[z].add(p),l[T].add(p),l[y].add(p))}let _=this.groups;_.length===0&&(_=[{start:0,count:e.count}]);for(let z=0,T=_.length;z<T;++z){const y=_[z],b=y.start,D=y.count;for(let L=b,N=b+D;L<N;L+=3)m(e.getX(L+0),e.getX(L+1),e.getX(L+2))}const v=new w,M=new w,S=new w,E=new w;function C(z){S.fromBufferAttribute(i,z),E.copy(S);const T=a[z];v.copy(T),v.sub(S.multiplyScalar(S.dot(T))).normalize(),M.crossVectors(E,T);const b=M.dot(l[z])<0?-1:1;o.setXYZW(z,v.x,v.y,v.z,b)}for(let z=0,T=_.length;z<T;++z){const y=_[z],b=y.start,D=y.count;for(let L=b,N=b+D;L<N;L+=3)C(e.getX(L+0)),C(e.getX(L+1)),C(e.getX(L+2))}}computeVertexNormals(){const e=this.index,t=this.getAttribute("position");if(t!==void 0){let n=this.getAttribute("normal");if(n===void 0)n=new kt(new Float32Array(t.count*3),3),this.setAttribute("normal",n);else for(let d=0,f=n.count;d<f;d++)n.setXYZ(d,0,0,0);const i=new w,r=new w,o=new w,a=new w,l=new w,c=new w,h=new w,u=new w;if(e)for(let d=0,f=e.count;d<f;d+=3){const g=e.getX(d+0),x=e.getX(d+1),p=e.getX(d+2);i.fromBufferAttribute(t,g),r.fromBufferAttribute(t,x),o.fromBufferAttribute(t,p),h.subVectors(o,r),u.subVectors(i,r),h.cross(u),a.fromBufferAttribute(n,g),l.fromBufferAttribute(n,x),c.fromBufferAttribute(n,p),a.add(h),l.add(h),c.add(h),n.setXYZ(g,a.x,a.y,a.z),n.setXYZ(x,l.x,l.y,l.z),n.setXYZ(p,c.x,c.y,c.z)}else for(let d=0,f=t.count;d<f;d+=3)i.fromBufferAttribute(t,d+0),r.fromBufferAttribute(t,d+1),o.fromBufferAttribute(t,d+2),h.subVectors(o,r),u.subVectors(i,r),h.cross(u),n.setXYZ(d+0,h.x,h.y,h.z),n.setXYZ(d+1,h.x,h.y,h.z),n.setXYZ(d+2,h.x,h.y,h.z);this.normalizeNormals(),n.needsUpdate=!0}}normalizeNormals(){const e=this.attributes.normal;for(let t=0,n=e.count;t<n;t++)Ot.fromBufferAttribute(e,t),Ot.normalize(),e.setXYZ(t,Ot.x,Ot.y,Ot.z)}toNonIndexed(){function e(a,l){const c=a.array,h=a.itemSize,u=a.normalized,d=new c.constructor(l.length*h);let f=0,g=0;for(let x=0,p=l.length;x<p;x++){a.isInterleavedBufferAttribute?f=l[x]*a.data.stride+a.offset:f=l[x]*h;for(let m=0;m<h;m++)d[g++]=c[f++]}return new kt(d,h,u)}if(this.index===null)return console.warn("THREE.BufferGeometry.toNonIndexed(): BufferGeometry is already non-indexed."),this;const t=new je,n=this.index.array,i=this.attributes;for(const a in i){const l=i[a],c=e(l,n);t.setAttribute(a,c)}const r=this.morphAttributes;for(const a in r){const l=[],c=r[a];for(let h=0,u=c.length;h<u;h++){const d=c[h],f=e(d,n);l.push(f)}t.morphAttributes[a]=l}t.morphTargetsRelative=this.morphTargetsRelative;const o=this.groups;for(let a=0,l=o.length;a<l;a++){const c=o[a];t.addGroup(c.start,c.count,c.materialIndex)}return t}toJSON(){const e={metadata:{version:4.6,type:"BufferGeometry",generator:"BufferGeometry.toJSON"}};if(e.uuid=this.uuid,e.type=this.type,this.name!==""&&(e.name=this.name),Object.keys(this.userData).length>0&&(e.userData=this.userData),this.parameters!==void 0){const l=this.parameters;for(const c in l)l[c]!==void 0&&(e[c]=l[c]);return e}e.data={attributes:{}};const t=this.index;t!==null&&(e.data.index={type:t.array.constructor.name,array:Array.prototype.slice.call(t.array)});const n=this.attributes;for(const l in n){const c=n[l];e.data.attributes[l]=c.toJSON(e.data)}const i={};let r=!1;for(const l in this.morphAttributes){const c=this.morphAttributes[l],h=[];for(let u=0,d=c.length;u<d;u++){const f=c[u];h.push(f.toJSON(e.data))}h.length>0&&(i[l]=h,r=!0)}r&&(e.data.morphAttributes=i,e.data.morphTargetsRelative=this.morphTargetsRelative);const o=this.groups;o.length>0&&(e.data.groups=JSON.parse(JSON.stringify(o)));const a=this.boundingSphere;return a!==null&&(e.data.boundingSphere={center:a.center.toArray(),radius:a.radius}),e}clone(){return new this.constructor().copy(this)}copy(e){this.index=null,this.attributes={},this.morphAttributes={},this.groups=[],this.boundingBox=null,this.boundingSphere=null;const t={};this.name=e.name;const n=e.index;n!==null&&this.setIndex(n.clone(t));const i=e.attributes;for(const c in i){const h=i[c];this.setAttribute(c,h.clone(t))}const r=e.morphAttributes;for(const c in r){const h=[],u=r[c];for(let d=0,f=u.length;d<f;d++)h.push(u[d].clone(t));this.morphAttributes[c]=h}this.morphTargetsRelative=e.morphTargetsRelative;const o=e.groups;for(let c=0,h=o.length;c<h;c++){const u=o[c];this.addGroup(u.start,u.count,u.materialIndex)}const a=e.boundingBox;a!==null&&(this.boundingBox=a.clone());const l=e.boundingSphere;return l!==null&&(this.boundingSphere=l.clone()),this.drawRange.start=e.drawRange.start,this.drawRange.count=e.drawRange.count,this.userData=e.userData,this}dispose(){this.dispatchEvent({type:"dispose"})}}const Gl=new Fe,oi=new bi,Qs=new Mi,Wl=new w,er=new w,tr=new w,nr=new w,To=new w,ir=new w,Xl=new w,sr=new w;class ve extends Mt{constructor(e=new je,t=new Ge){super(),this.isMesh=!0,this.type="Mesh",this.geometry=e,this.material=t,this.updateMorphTargets()}copy(e,t){return super.copy(e,t),e.morphTargetInfluences!==void 0&&(this.morphTargetInfluences=e.morphTargetInfluences.slice()),e.morphTargetDictionary!==void 0&&(this.morphTargetDictionary=Object.assign({},e.morphTargetDictionary)),this.material=Array.isArray(e.material)?e.material.slice():e.material,this.geometry=e.geometry,this}updateMorphTargets(){const t=this.geometry.morphAttributes,n=Object.keys(t);if(n.length>0){const i=t[n[0]];if(i!==void 0){this.morphTargetInfluences=[],this.morphTargetDictionary={};for(let r=0,o=i.length;r<o;r++){const a=i[r].name||String(r);this.morphTargetInfluences.push(0),this.morphTargetDictionary[a]=r}}}}getVertexPosition(e,t){const n=this.geometry,i=n.attributes.position,r=n.morphAttributes.position,o=n.morphTargetsRelative;t.fromBufferAttribute(i,e);const a=this.morphTargetInfluences;if(r&&a){ir.set(0,0,0);for(let l=0,c=r.length;l<c;l++){const h=a[l],u=r[l];h!==0&&(To.fromBufferAttribute(u,e),o?ir.addScaledVector(To,h):ir.addScaledVector(To.sub(t),h))}t.add(ir)}return t}raycast(e,t){const n=this.geometry,i=this.material,r=this.matrixWorld;i!==void 0&&(n.boundingSphere===null&&n.computeBoundingSphere(),Qs.copy(n.boundingSphere),Qs.applyMatrix4(r),oi.copy(e.ray).recast(e.near),!(Qs.containsPoint(oi.origin)===!1&&(oi.intersectSphere(Qs,Wl)===null||oi.origin.distanceToSquared(Wl)>(e.far-e.near)**2))&&(Gl.copy(r).invert(),oi.copy(e.ray).applyMatrix4(Gl),!(n.boundingBox!==null&&oi.intersectsBox(n.boundingBox)===!1)&&this._computeIntersections(e,t,oi)))}_computeIntersections(e,t,n){let i;const r=this.geometry,o=this.material,a=r.index,l=r.attributes.position,c=r.attributes.uv,h=r.attributes.uv1,u=r.attributes.normal,d=r.groups,f=r.drawRange;if(a!==null)if(Array.isArray(o))for(let g=0,x=d.length;g<x;g++){const p=d[g],m=o[p.materialIndex],_=Math.max(p.start,f.start),v=Math.min(a.count,Math.min(p.start+p.count,f.start+f.count));for(let M=_,S=v;M<S;M+=3){const E=a.getX(M),C=a.getX(M+1),z=a.getX(M+2);i=rr(this,m,e,n,c,h,u,E,C,z),i&&(i.faceIndex=Math.floor(M/3),i.face.materialIndex=p.materialIndex,t.push(i))}}else{const g=Math.max(0,f.start),x=Math.min(a.count,f.start+f.count);for(let p=g,m=x;p<m;p+=3){const _=a.getX(p),v=a.getX(p+1),M=a.getX(p+2);i=rr(this,o,e,n,c,h,u,_,v,M),i&&(i.faceIndex=Math.floor(p/3),t.push(i))}}else if(l!==void 0)if(Array.isArray(o))for(let g=0,x=d.length;g<x;g++){const p=d[g],m=o[p.materialIndex],_=Math.max(p.start,f.start),v=Math.min(l.count,Math.min(p.start+p.count,f.start+f.count));for(let M=_,S=v;M<S;M+=3){const E=M,C=M+1,z=M+2;i=rr(this,m,e,n,c,h,u,E,C,z),i&&(i.faceIndex=Math.floor(M/3),i.face.materialIndex=p.materialIndex,t.push(i))}}else{const g=Math.max(0,f.start),x=Math.min(l.count,f.start+f.count);for(let p=g,m=x;p<m;p+=3){const _=p,v=p+1,M=p+2;i=rr(this,o,e,n,c,h,u,_,v,M),i&&(i.faceIndex=Math.floor(p/3),t.push(i))}}}}function Wd(s,e,t,n,i,r,o,a){let l;if(e.side===Ht?l=n.intersectTriangle(o,r,i,!0,a):l=n.intersectTriangle(i,r,o,e.side===wn,a),l===null)return null;sr.copy(a),sr.applyMatrix4(s.matrixWorld);const c=t.ray.origin.distanceTo(sr);return c<t.near||c>t.far?null:{distance:c,point:sr.clone(),object:s}}function rr(s,e,t,n,i,r,o,a,l,c){s.getVertexPosition(a,er),s.getVertexPosition(l,tr),s.getVertexPosition(c,nr);const h=Wd(s,e,t,n,er,tr,nr,Xl);if(h){const u=new w;cn.getBarycoord(Xl,er,tr,nr,u),i&&(h.uv=cn.getInterpolatedAttribute(i,a,l,c,u,new Q)),r&&(h.uv1=cn.getInterpolatedAttribute(r,a,l,c,u,new Q)),o&&(h.normal=cn.getInterpolatedAttribute(o,a,l,c,u,new w),h.normal.dot(n.direction)>0&&h.normal.multiplyScalar(-1));const d={a,b:l,c,normal:new w,materialIndex:0};cn.getNormal(er,tr,nr,d.normal),h.face=d,h.barycoord=u}return h}class lt extends je{constructor(e=1,t=1,n=1,i=1,r=1,o=1){super(),this.type="BoxGeometry",this.parameters={width:e,height:t,depth:n,widthSegments:i,heightSegments:r,depthSegments:o};const a=this;i=Math.floor(i),r=Math.floor(r),o=Math.floor(o);const l=[],c=[],h=[],u=[];let d=0,f=0;g("z","y","x",-1,-1,n,t,e,o,r,0),g("z","y","x",1,-1,n,t,-e,o,r,1),g("x","z","y",1,1,e,n,t,i,o,2),g("x","z","y",1,-1,e,n,-t,i,o,3),g("x","y","z",1,-1,e,t,n,i,r,4),g("x","y","z",-1,-1,e,t,-n,i,r,5),this.setIndex(l),this.setAttribute("position",new Ae(c,3)),this.setAttribute("normal",new Ae(h,3)),this.setAttribute("uv",new Ae(u,2));function g(x,p,m,_,v,M,S,E,C,z,T){const y=M/C,b=S/z,D=M/2,L=S/2,N=E/2,B=C+1,k=z+1;let q=0,U=0;const V=new w;for(let P=0;P<k;P++){const O=P*b-L;for(let H=0;H<B;H++){const Z=H*y-D;V[x]=Z*_,V[p]=O*v,V[m]=N,c.push(V.x,V.y,V.z),V[x]=0,V[p]=0,V[m]=E>0?1:-1,h.push(V.x,V.y,V.z),u.push(H/C),u.push(1-P/z),q+=1}}for(let P=0;P<z;P++)for(let O=0;O<C;O++){const H=d+O+B*P,Z=d+O+B*(P+1),W=d+(O+1)+B*(P+1),$=d+(O+1)+B*P;l.push(H,Z,$),l.push(Z,W,$),U+=6}a.addGroup(f,U,T),f+=U,d+=q}}copy(e){return super.copy(e),this.parameters=Object.assign({},e.parameters),this}static fromJSON(e){return new lt(e.width,e.height,e.depth,e.widthSegments,e.heightSegments,e.depthSegments)}}function is(s){const e={};for(const t in s){e[t]={};for(const n in s[t]){const i=s[t][n];i&&(i.isColor||i.isMatrix3||i.isMatrix4||i.isVector2||i.isVector3||i.isVector4||i.isTexture||i.isQuaternion)?i.isRenderTargetTexture?(console.warn("UniformsUtils: Textures of render targets cannot be cloned via cloneUniforms() or mergeUniforms()."),e[t][n]=null):e[t][n]=i.clone():Array.isArray(i)?e[t][n]=i.slice():e[t][n]=i}}return e}function Xt(s){const e={};for(let t=0;t<s.length;t++){const n=is(s[t]);for(const i in n)e[i]=n[i]}return e}function Xd(s){const e=[];for(let t=0;t<s.length;t++)e.push(s[t].clone());return e}function Nh(s){const e=s.getRenderTarget();return e===null?s.outputColorSpace:e.isXRRenderTarget===!0?e.texture.colorSpace:nt.workingColorSpace}const Is={clone:is,merge:Xt};var Yd=`void main() {
	gl_Position = projectionMatrix * modelViewMatrix * vec4( position, 1.0 );
}`,qd=`void main() {
	gl_FragColor = vec4( 1.0, 0.0, 0.0, 1.0 );
}`;class gt extends wi{constructor(e){super(),this.isShaderMaterial=!0,this.type="ShaderMaterial",this.defines={},this.uniforms={},this.uniformsGroups=[],this.vertexShader=Yd,this.fragmentShader=qd,this.linewidth=1,this.wireframe=!1,this.wireframeLinewidth=1,this.fog=!1,this.lights=!1,this.clipping=!1,this.forceSinglePass=!0,this.extensions={clipCullDistance:!1,multiDraw:!1},this.defaultAttributeValues={color:[1,1,1],uv:[0,0],uv1:[0,0]},this.index0AttributeName=void 0,this.uniformsNeedUpdate=!1,this.glslVersion=null,e!==void 0&&this.setValues(e)}copy(e){return super.copy(e),this.fragmentShader=e.fragmentShader,this.vertexShader=e.vertexShader,this.uniforms=is(e.uniforms),this.uniformsGroups=Xd(e.uniformsGroups),this.defines=Object.assign({},e.defines),this.wireframe=e.wireframe,this.wireframeLinewidth=e.wireframeLinewidth,this.fog=e.fog,this.lights=e.lights,this.clipping=e.clipping,this.extensions=Object.assign({},e.extensions),this.glslVersion=e.glslVersion,this}toJSON(e){const t=super.toJSON(e);t.glslVersion=this.glslVersion,t.uniforms={};for(const i in this.uniforms){const o=this.uniforms[i].value;o&&o.isTexture?t.uniforms[i]={type:"t",value:o.toJSON(e).uuid}:o&&o.isColor?t.uniforms[i]={type:"c",value:o.getHex()}:o&&o.isVector2?t.uniforms[i]={type:"v2",value:o.toArray()}:o&&o.isVector3?t.uniforms[i]={type:"v3",value:o.toArray()}:o&&o.isVector4?t.uniforms[i]={type:"v4",value:o.toArray()}:o&&o.isMatrix3?t.uniforms[i]={type:"m3",value:o.toArray()}:o&&o.isMatrix4?t.uniforms[i]={type:"m4",value:o.toArray()}:t.uniforms[i]={value:o}}Object.keys(this.defines).length>0&&(t.defines=this.defines),t.vertexShader=this.vertexShader,t.fragmentShader=this.fragmentShader,t.lights=this.lights,t.clipping=this.clipping;const n={};for(const i in this.extensions)this.extensions[i]===!0&&(n[i]=!0);return Object.keys(n).length>0&&(t.extensions=n),t}}class Uh extends Mt{constructor(){super(),this.isCamera=!0,this.type="Camera",this.matrixWorldInverse=new Fe,this.projectionMatrix=new Fe,this.projectionMatrixInverse=new Fe,this.coordinateSystem=zn}copy(e,t){return super.copy(e,t),this.matrixWorldInverse.copy(e.matrixWorldInverse),this.projectionMatrix.copy(e.projectionMatrix),this.projectionMatrixInverse.copy(e.projectionMatrixInverse),this.coordinateSystem=e.coordinateSystem,this}getWorldDirection(e){return super.getWorldDirection(e).negate()}updateMatrixWorld(e){super.updateMatrixWorld(e),this.matrixWorldInverse.copy(this.matrixWorld).invert()}updateWorldMatrix(e,t){super.updateWorldMatrix(e,t),this.matrixWorldInverse.copy(this.matrixWorld).invert()}clone(){return new this.constructor().copy(this)}}const Kn=new w,Yl=new Q,ql=new Q;class Jt extends Uh{constructor(e=50,t=1,n=.1,i=2e3){super(),this.isPerspectiveCamera=!0,this.type="PerspectiveCamera",this.fov=e,this.zoom=1,this.near=n,this.far=i,this.focus=10,this.aspect=t,this.view=null,this.filmGauge=35,this.filmOffset=0,this.updateProjectionMatrix()}copy(e,t){return super.copy(e,t),this.fov=e.fov,this.zoom=e.zoom,this.near=e.near,this.far=e.far,this.focus=e.focus,this.aspect=e.aspect,this.view=e.view===null?null:Object.assign({},e.view),this.filmGauge=e.filmGauge,this.filmOffset=e.filmOffset,this}setFocalLength(e){const t=.5*this.getFilmHeight()/e;this.fov=ns*2*Math.atan(t),this.updateProjectionMatrix()}getFocalLength(){const e=Math.tan(Ss*.5*this.fov);return .5*this.getFilmHeight()/e}getEffectiveFOV(){return ns*2*Math.atan(Math.tan(Ss*.5*this.fov)/this.zoom)}getFilmWidth(){return this.filmGauge*Math.min(this.aspect,1)}getFilmHeight(){return this.filmGauge/Math.max(this.aspect,1)}getViewBounds(e,t,n){Kn.set(-1,-1,.5).applyMatrix4(this.projectionMatrixInverse),t.set(Kn.x,Kn.y).multiplyScalar(-e/Kn.z),Kn.set(1,1,.5).applyMatrix4(this.projectionMatrixInverse),n.set(Kn.x,Kn.y).multiplyScalar(-e/Kn.z)}getViewSize(e,t){return this.getViewBounds(e,Yl,ql),t.subVectors(ql,Yl)}setViewOffset(e,t,n,i,r,o){this.aspect=e/t,this.view===null&&(this.view={enabled:!0,fullWidth:1,fullHeight:1,offsetX:0,offsetY:0,width:1,height:1}),this.view.enabled=!0,this.view.fullWidth=e,this.view.fullHeight=t,this.view.offsetX=n,this.view.offsetY=i,this.view.width=r,this.view.height=o,this.updateProjectionMatrix()}clearViewOffset(){this.view!==null&&(this.view.enabled=!1),this.updateProjectionMatrix()}updateProjectionMatrix(){const e=this.near;let t=e*Math.tan(Ss*.5*this.fov)/this.zoom,n=2*t,i=this.aspect*n,r=-.5*i;const o=this.view;if(this.view!==null&&this.view.enabled){const l=o.fullWidth,c=o.fullHeight;r+=o.offsetX*i/l,t-=o.offsetY*n/c,i*=o.width/l,n*=o.height/c}const a=this.filmOffset;a!==0&&(r+=e*a/this.getFilmWidth()),this.projectionMatrix.makePerspective(r,r+i,t,t-n,e,this.far,this.coordinateSystem),this.projectionMatrixInverse.copy(this.projectionMatrix).invert()}toJSON(e){const t=super.toJSON(e);return t.object.fov=this.fov,t.object.zoom=this.zoom,t.object.near=this.near,t.object.far=this.far,t.object.focus=this.focus,t.object.aspect=this.aspect,this.view!==null&&(t.object.view=Object.assign({},this.view)),t.object.filmGauge=this.filmGauge,t.object.filmOffset=this.filmOffset,t}}const Fi=-90,zi=1;class jd extends Mt{constructor(e,t,n){super(),this.type="CubeCamera",this.renderTarget=n,this.coordinateSystem=null,this.activeMipmapLevel=0;const i=new Jt(Fi,zi,e,t);i.layers=this.layers,this.add(i);const r=new Jt(Fi,zi,e,t);r.layers=this.layers,this.add(r);const o=new Jt(Fi,zi,e,t);o.layers=this.layers,this.add(o);const a=new Jt(Fi,zi,e,t);a.layers=this.layers,this.add(a);const l=new Jt(Fi,zi,e,t);l.layers=this.layers,this.add(l);const c=new Jt(Fi,zi,e,t);c.layers=this.layers,this.add(c)}updateCoordinateSystem(){const e=this.coordinateSystem,t=this.children.concat(),[n,i,r,o,a,l]=t;for(const c of t)this.remove(c);if(e===zn)n.up.set(0,1,0),n.lookAt(1,0,0),i.up.set(0,1,0),i.lookAt(-1,0,0),r.up.set(0,0,-1),r.lookAt(0,1,0),o.up.set(0,0,1),o.lookAt(0,-1,0),a.up.set(0,1,0),a.lookAt(0,0,1),l.up.set(0,1,0),l.lookAt(0,0,-1);else if(e===Ur)n.up.set(0,-1,0),n.lookAt(-1,0,0),i.up.set(0,-1,0),i.lookAt(1,0,0),r.up.set(0,0,1),r.lookAt(0,1,0),o.up.set(0,0,-1),o.lookAt(0,-1,0),a.up.set(0,-1,0),a.lookAt(0,0,1),l.up.set(0,-1,0),l.lookAt(0,0,-1);else throw new Error("THREE.CubeCamera.updateCoordinateSystem(): Invalid coordinate system: "+e);for(const c of t)this.add(c),c.updateMatrixWorld()}update(e,t){this.parent===null&&this.updateMatrixWorld();const{renderTarget:n,activeMipmapLevel:i}=this;this.coordinateSystem!==e.coordinateSystem&&(this.coordinateSystem=e.coordinateSystem,this.updateCoordinateSystem());const[r,o,a,l,c,h]=this.children,u=e.getRenderTarget(),d=e.getActiveCubeFace(),f=e.getActiveMipmapLevel(),g=e.xr.enabled;e.xr.enabled=!1;const x=n.texture.generateMipmaps;n.texture.generateMipmaps=!1,e.setRenderTarget(n,0,i),e.render(t,r),e.setRenderTarget(n,1,i),e.render(t,o),e.setRenderTarget(n,2,i),e.render(t,a),e.setRenderTarget(n,3,i),e.render(t,l),e.setRenderTarget(n,4,i),e.render(t,c),n.texture.generateMipmaps=x,e.setRenderTarget(n,5,i),e.render(t,h),e.setRenderTarget(u,d,f),e.xr.enabled=g,n.texture.needsPMREMUpdate=!0}}class Oh extends It{constructor(e,t,n,i,r,o,a,l,c,h){e=e!==void 0?e:[],t=t!==void 0?t:$i,super(e,t,n,i,r,o,a,l,c,h),this.isCubeTexture=!0,this.flipY=!1}get images(){return this.image}set images(e){this.image=e}}class Kd extends un{constructor(e=1,t={}){super(e,e,t),this.isWebGLCubeRenderTarget=!0;const n={width:e,height:e,depth:1},i=[n,n,n,n,n,n];this.texture=new Oh(i,t.mapping,t.wrapS,t.wrapT,t.magFilter,t.minFilter,t.format,t.type,t.anisotropy,t.colorSpace),this.texture.isRenderTargetTexture=!0,this.texture.generateMipmaps=t.generateMipmaps!==void 0?t.generateMipmaps:!1,this.texture.minFilter=t.minFilter!==void 0?t.minFilter:Ct}fromEquirectangularTexture(e,t){this.texture.type=t.type,this.texture.colorSpace=t.colorSpace,this.texture.generateMipmaps=t.generateMipmaps,this.texture.minFilter=t.minFilter,this.texture.magFilter=t.magFilter;const n={uniforms:{tEquirect:{value:null}},vertexShader:`

				varying vec3 vWorldDirection;

				vec3 transformDirection( in vec3 dir, in mat4 matrix ) {

					return normalize( ( matrix * vec4( dir, 0.0 ) ).xyz );

				}

				void main() {

					vWorldDirection = transformDirection( position, modelMatrix );

					#include <begin_vertex>
					#include <project_vertex>

				}
			`,fragmentShader:`

				uniform sampler2D tEquirect;

				varying vec3 vWorldDirection;

				#include <common>

				void main() {

					vec3 direction = normalize( vWorldDirection );

					vec2 sampleUV = equirectUv( direction );

					gl_FragColor = texture2D( tEquirect, sampleUV );

				}
			`},i=new lt(5,5,5),r=new gt({name:"CubemapFromEquirect",uniforms:is(n.uniforms),vertexShader:n.vertexShader,fragmentShader:n.fragmentShader,side:Ht,blending:kn});r.uniforms.tEquirect.value=t;const o=new ve(i,r),a=t.minFilter;return t.minFilter===pi&&(t.minFilter=Ct),new jd(1,10,this).update(e,o),t.minFilter=a,o.geometry.dispose(),o.material.dispose(),this}clear(e,t,n,i){const r=e.getRenderTarget();for(let o=0;o<6;o++)e.setRenderTarget(this,o),e.clear(t,n,i);e.setRenderTarget(r)}}const Eo=new w,Zd=new w,Jd=new Ye;class Jn{constructor(e=new w(1,0,0),t=0){this.isPlane=!0,this.normal=e,this.constant=t}set(e,t){return this.normal.copy(e),this.constant=t,this}setComponents(e,t,n,i){return this.normal.set(e,t,n),this.constant=i,this}setFromNormalAndCoplanarPoint(e,t){return this.normal.copy(e),this.constant=-t.dot(this.normal),this}setFromCoplanarPoints(e,t,n){const i=Eo.subVectors(n,t).cross(Zd.subVectors(e,t)).normalize();return this.setFromNormalAndCoplanarPoint(i,e),this}copy(e){return this.normal.copy(e.normal),this.constant=e.constant,this}normalize(){const e=1/this.normal.length();return this.normal.multiplyScalar(e),this.constant*=e,this}negate(){return this.constant*=-1,this.normal.negate(),this}distanceToPoint(e){return this.normal.dot(e)+this.constant}distanceToSphere(e){return this.distanceToPoint(e.center)-e.radius}projectPoint(e,t){return t.copy(e).addScaledVector(this.normal,-this.distanceToPoint(e))}intersectLine(e,t){const n=e.delta(Eo),i=this.normal.dot(n);if(i===0)return this.distanceToPoint(e.start)===0?t.copy(e.start):null;const r=-(e.start.dot(this.normal)+this.constant)/i;return r<0||r>1?null:t.copy(e.start).addScaledVector(n,r)}intersectsLine(e){const t=this.distanceToPoint(e.start),n=this.distanceToPoint(e.end);return t<0&&n>0||n<0&&t>0}intersectsBox(e){return e.intersectsPlane(this)}intersectsSphere(e){return e.intersectsPlane(this)}coplanarPoint(e){return e.copy(this.normal).multiplyScalar(-this.constant)}applyMatrix4(e,t){const n=t||Jd.getNormalMatrix(e),i=this.coplanarPoint(Eo).applyMatrix4(e),r=this.normal.applyMatrix3(n).normalize();return this.constant=-i.dot(r),this}translate(e){return this.constant-=e.dot(this.normal),this}equals(e){return e.normal.equals(this.normal)&&e.constant===this.constant}clone(){return new this.constructor().copy(this)}}const ai=new Mi,or=new w;class el{constructor(e=new Jn,t=new Jn,n=new Jn,i=new Jn,r=new Jn,o=new Jn){this.planes=[e,t,n,i,r,o]}set(e,t,n,i,r,o){const a=this.planes;return a[0].copy(e),a[1].copy(t),a[2].copy(n),a[3].copy(i),a[4].copy(r),a[5].copy(o),this}copy(e){const t=this.planes;for(let n=0;n<6;n++)t[n].copy(e.planes[n]);return this}setFromProjectionMatrix(e,t=zn){const n=this.planes,i=e.elements,r=i[0],o=i[1],a=i[2],l=i[3],c=i[4],h=i[5],u=i[6],d=i[7],f=i[8],g=i[9],x=i[10],p=i[11],m=i[12],_=i[13],v=i[14],M=i[15];if(n[0].setComponents(l-r,d-c,p-f,M-m).normalize(),n[1].setComponents(l+r,d+c,p+f,M+m).normalize(),n[2].setComponents(l+o,d+h,p+g,M+_).normalize(),n[3].setComponents(l-o,d-h,p-g,M-_).normalize(),n[4].setComponents(l-a,d-u,p-x,M-v).normalize(),t===zn)n[5].setComponents(l+a,d+u,p+x,M+v).normalize();else if(t===Ur)n[5].setComponents(a,u,x,v).normalize();else throw new Error("THREE.Frustum.setFromProjectionMatrix(): Invalid coordinate system: "+t);return this}intersectsObject(e){if(e.boundingSphere!==void 0)e.boundingSphere===null&&e.computeBoundingSphere(),ai.copy(e.boundingSphere).applyMatrix4(e.matrixWorld);else{const t=e.geometry;t.boundingSphere===null&&t.computeBoundingSphere(),ai.copy(t.boundingSphere).applyMatrix4(e.matrixWorld)}return this.intersectsSphere(ai)}intersectsSprite(e){return ai.center.set(0,0,0),ai.radius=.7071067811865476,ai.applyMatrix4(e.matrixWorld),this.intersectsSphere(ai)}intersectsSphere(e){const t=this.planes,n=e.center,i=-e.radius;for(let r=0;r<6;r++)if(t[r].distanceToPoint(n)<i)return!1;return!0}intersectsBox(e){const t=this.planes;for(let n=0;n<6;n++){const i=t[n];if(or.x=i.normal.x>0?e.max.x:e.min.x,or.y=i.normal.y>0?e.max.y:e.min.y,or.z=i.normal.z>0?e.max.z:e.min.z,i.distanceToPoint(or)<0)return!1}return!0}containsPoint(e){const t=this.planes;for(let n=0;n<6;n++)if(t[n].distanceToPoint(e)<0)return!1;return!0}clone(){return new this.constructor().copy(this)}}function Fh(){let s=null,e=!1,t=null,n=null;function i(r,o){t(r,o),n=s.requestAnimationFrame(i)}return{start:function(){e!==!0&&t!==null&&(n=s.requestAnimationFrame(i),e=!0)},stop:function(){s.cancelAnimationFrame(n),e=!1},setAnimationLoop:function(r){t=r},setContext:function(r){s=r}}}function $d(s){const e=new WeakMap;function t(a,l){const c=a.array,h=a.usage,u=c.byteLength,d=s.createBuffer();s.bindBuffer(l,d),s.bufferData(l,c,h),a.onUploadCallback();let f;if(c instanceof Float32Array)f=s.FLOAT;else if(c instanceof Uint16Array)a.isFloat16BufferAttribute?f=s.HALF_FLOAT:f=s.UNSIGNED_SHORT;else if(c instanceof Int16Array)f=s.SHORT;else if(c instanceof Uint32Array)f=s.UNSIGNED_INT;else if(c instanceof Int32Array)f=s.INT;else if(c instanceof Int8Array)f=s.BYTE;else if(c instanceof Uint8Array)f=s.UNSIGNED_BYTE;else if(c instanceof Uint8ClampedArray)f=s.UNSIGNED_BYTE;else throw new Error("THREE.WebGLAttributes: Unsupported buffer data format: "+c);return{buffer:d,type:f,bytesPerElement:c.BYTES_PER_ELEMENT,version:a.version,size:u}}function n(a,l,c){const h=l.array,u=l.updateRanges;if(s.bindBuffer(c,a),u.length===0)s.bufferSubData(c,0,h);else{u.sort((f,g)=>f.start-g.start);let d=0;for(let f=1;f<u.length;f++){const g=u[d],x=u[f];x.start<=g.start+g.count+1?g.count=Math.max(g.count,x.start+x.count-g.start):(++d,u[d]=x)}u.length=d+1;for(let f=0,g=u.length;f<g;f++){const x=u[f];s.bufferSubData(c,x.start*h.BYTES_PER_ELEMENT,h,x.start,x.count)}l.clearUpdateRanges()}l.onUploadCallback()}function i(a){return a.isInterleavedBufferAttribute&&(a=a.data),e.get(a)}function r(a){a.isInterleavedBufferAttribute&&(a=a.data);const l=e.get(a);l&&(s.deleteBuffer(l.buffer),e.delete(a))}function o(a,l){if(a.isInterleavedBufferAttribute&&(a=a.data),a.isGLBufferAttribute){const h=e.get(a);(!h||h.version<a.version)&&e.set(a,{buffer:a.buffer,type:a.type,bytesPerElement:a.elementSize,version:a.version});return}const c=e.get(a);if(c===void 0)e.set(a,t(a,l));else if(c.version<a.version){if(c.size!==a.array.byteLength)throw new Error("THREE.WebGLAttributes: The size of the buffer attribute's array buffer does not match the original size. Resizing buffer attributes is not supported.");n(c.buffer,a,l),c.version=a.version}}return{get:i,remove:r,update:o}}class Gt extends je{constructor(e=1,t=1,n=1,i=1){super(),this.type="PlaneGeometry",this.parameters={width:e,height:t,widthSegments:n,heightSegments:i};const r=e/2,o=t/2,a=Math.floor(n),l=Math.floor(i),c=a+1,h=l+1,u=e/a,d=t/l,f=[],g=[],x=[],p=[];for(let m=0;m<h;m++){const _=m*d-o;for(let v=0;v<c;v++){const M=v*u-r;g.push(M,-_,0),x.push(0,0,1),p.push(v/a),p.push(1-m/l)}}for(let m=0;m<l;m++)for(let _=0;_<a;_++){const v=_+c*m,M=_+c*(m+1),S=_+1+c*(m+1),E=_+1+c*m;f.push(v,M,E),f.push(M,S,E)}this.setIndex(f),this.setAttribute("position",new Ae(g,3)),this.setAttribute("normal",new Ae(x,3)),this.setAttribute("uv",new Ae(p,2))}copy(e){return super.copy(e),this.parameters=Object.assign({},e.parameters),this}static fromJSON(e){return new Gt(e.width,e.height,e.widthSegments,e.heightSegments)}}var Qd=`#ifdef USE_ALPHAHASH
	if ( diffuseColor.a < getAlphaHashThreshold( vPosition ) ) discard;
#endif`,ef=`#ifdef USE_ALPHAHASH
	const float ALPHA_HASH_SCALE = 0.05;
	float hash2D( vec2 value ) {
		return fract( 1.0e4 * sin( 17.0 * value.x + 0.1 * value.y ) * ( 0.1 + abs( sin( 13.0 * value.y + value.x ) ) ) );
	}
	float hash3D( vec3 value ) {
		return hash2D( vec2( hash2D( value.xy ), value.z ) );
	}
	float getAlphaHashThreshold( vec3 position ) {
		float maxDeriv = max(
			length( dFdx( position.xyz ) ),
			length( dFdy( position.xyz ) )
		);
		float pixScale = 1.0 / ( ALPHA_HASH_SCALE * maxDeriv );
		vec2 pixScales = vec2(
			exp2( floor( log2( pixScale ) ) ),
			exp2( ceil( log2( pixScale ) ) )
		);
		vec2 alpha = vec2(
			hash3D( floor( pixScales.x * position.xyz ) ),
			hash3D( floor( pixScales.y * position.xyz ) )
		);
		float lerpFactor = fract( log2( pixScale ) );
		float x = ( 1.0 - lerpFactor ) * alpha.x + lerpFactor * alpha.y;
		float a = min( lerpFactor, 1.0 - lerpFactor );
		vec3 cases = vec3(
			x * x / ( 2.0 * a * ( 1.0 - a ) ),
			( x - 0.5 * a ) / ( 1.0 - a ),
			1.0 - ( ( 1.0 - x ) * ( 1.0 - x ) / ( 2.0 * a * ( 1.0 - a ) ) )
		);
		float threshold = ( x < ( 1.0 - a ) )
			? ( ( x < a ) ? cases.x : cases.y )
			: cases.z;
		return clamp( threshold , 1.0e-6, 1.0 );
	}
#endif`,tf=`#ifdef USE_ALPHAMAP
	diffuseColor.a *= texture2D( alphaMap, vAlphaMapUv ).g;
#endif`,nf=`#ifdef USE_ALPHAMAP
	uniform sampler2D alphaMap;
#endif`,sf=`#ifdef USE_ALPHATEST
	#ifdef ALPHA_TO_COVERAGE
	diffuseColor.a = smoothstep( alphaTest, alphaTest + fwidth( diffuseColor.a ), diffuseColor.a );
	if ( diffuseColor.a == 0.0 ) discard;
	#else
	if ( diffuseColor.a < alphaTest ) discard;
	#endif
#endif`,rf=`#ifdef USE_ALPHATEST
	uniform float alphaTest;
#endif`,of=`#ifdef USE_AOMAP
	float ambientOcclusion = ( texture2D( aoMap, vAoMapUv ).r - 1.0 ) * aoMapIntensity + 1.0;
	reflectedLight.indirectDiffuse *= ambientOcclusion;
	#if defined( USE_CLEARCOAT ) 
		clearcoatSpecularIndirect *= ambientOcclusion;
	#endif
	#if defined( USE_SHEEN ) 
		sheenSpecularIndirect *= ambientOcclusion;
	#endif
	#if defined( USE_ENVMAP ) && defined( STANDARD )
		float dotNV = saturate( dot( geometryNormal, geometryViewDir ) );
		reflectedLight.indirectSpecular *= computeSpecularOcclusion( dotNV, ambientOcclusion, material.roughness );
	#endif
#endif`,af=`#ifdef USE_AOMAP
	uniform sampler2D aoMap;
	uniform float aoMapIntensity;
#endif`,lf=`#ifdef USE_BATCHING
	#if ! defined( GL_ANGLE_multi_draw )
	#define gl_DrawID _gl_DrawID
	uniform int _gl_DrawID;
	#endif
	uniform highp sampler2D batchingTexture;
	uniform highp usampler2D batchingIdTexture;
	mat4 getBatchingMatrix( const in float i ) {
		int size = textureSize( batchingTexture, 0 ).x;
		int j = int( i ) * 4;
		int x = j % size;
		int y = j / size;
		vec4 v1 = texelFetch( batchingTexture, ivec2( x, y ), 0 );
		vec4 v2 = texelFetch( batchingTexture, ivec2( x + 1, y ), 0 );
		vec4 v3 = texelFetch( batchingTexture, ivec2( x + 2, y ), 0 );
		vec4 v4 = texelFetch( batchingTexture, ivec2( x + 3, y ), 0 );
		return mat4( v1, v2, v3, v4 );
	}
	float getIndirectIndex( const in int i ) {
		int size = textureSize( batchingIdTexture, 0 ).x;
		int x = i % size;
		int y = i / size;
		return float( texelFetch( batchingIdTexture, ivec2( x, y ), 0 ).r );
	}
#endif
#ifdef USE_BATCHING_COLOR
	uniform sampler2D batchingColorTexture;
	vec3 getBatchingColor( const in float i ) {
		int size = textureSize( batchingColorTexture, 0 ).x;
		int j = int( i );
		int x = j % size;
		int y = j / size;
		return texelFetch( batchingColorTexture, ivec2( x, y ), 0 ).rgb;
	}
#endif`,cf=`#ifdef USE_BATCHING
	mat4 batchingMatrix = getBatchingMatrix( getIndirectIndex( gl_DrawID ) );
#endif`,hf=`vec3 transformed = vec3( position );
#ifdef USE_ALPHAHASH
	vPosition = vec3( position );
#endif`,uf=`vec3 objectNormal = vec3( normal );
#ifdef USE_TANGENT
	vec3 objectTangent = vec3( tangent.xyz );
#endif`,df=`float G_BlinnPhong_Implicit( ) {
	return 0.25;
}
float D_BlinnPhong( const in float shininess, const in float dotNH ) {
	return RECIPROCAL_PI * ( shininess * 0.5 + 1.0 ) * pow( dotNH, shininess );
}
vec3 BRDF_BlinnPhong( const in vec3 lightDir, const in vec3 viewDir, const in vec3 normal, const in vec3 specularColor, const in float shininess ) {
	vec3 halfDir = normalize( lightDir + viewDir );
	float dotNH = saturate( dot( normal, halfDir ) );
	float dotVH = saturate( dot( viewDir, halfDir ) );
	vec3 F = F_Schlick( specularColor, 1.0, dotVH );
	float G = G_BlinnPhong_Implicit( );
	float D = D_BlinnPhong( shininess, dotNH );
	return F * ( G * D );
} // validated`,ff=`#ifdef USE_IRIDESCENCE
	const mat3 XYZ_TO_REC709 = mat3(
		 3.2404542, -0.9692660,  0.0556434,
		-1.5371385,  1.8760108, -0.2040259,
		-0.4985314,  0.0415560,  1.0572252
	);
	vec3 Fresnel0ToIor( vec3 fresnel0 ) {
		vec3 sqrtF0 = sqrt( fresnel0 );
		return ( vec3( 1.0 ) + sqrtF0 ) / ( vec3( 1.0 ) - sqrtF0 );
	}
	vec3 IorToFresnel0( vec3 transmittedIor, float incidentIor ) {
		return pow2( ( transmittedIor - vec3( incidentIor ) ) / ( transmittedIor + vec3( incidentIor ) ) );
	}
	float IorToFresnel0( float transmittedIor, float incidentIor ) {
		return pow2( ( transmittedIor - incidentIor ) / ( transmittedIor + incidentIor ));
	}
	vec3 evalSensitivity( float OPD, vec3 shift ) {
		float phase = 2.0 * PI * OPD * 1.0e-9;
		vec3 val = vec3( 5.4856e-13, 4.4201e-13, 5.2481e-13 );
		vec3 pos = vec3( 1.6810e+06, 1.7953e+06, 2.2084e+06 );
		vec3 var = vec3( 4.3278e+09, 9.3046e+09, 6.6121e+09 );
		vec3 xyz = val * sqrt( 2.0 * PI * var ) * cos( pos * phase + shift ) * exp( - pow2( phase ) * var );
		xyz.x += 9.7470e-14 * sqrt( 2.0 * PI * 4.5282e+09 ) * cos( 2.2399e+06 * phase + shift[ 0 ] ) * exp( - 4.5282e+09 * pow2( phase ) );
		xyz /= 1.0685e-7;
		vec3 rgb = XYZ_TO_REC709 * xyz;
		return rgb;
	}
	vec3 evalIridescence( float outsideIOR, float eta2, float cosTheta1, float thinFilmThickness, vec3 baseF0 ) {
		vec3 I;
		float iridescenceIOR = mix( outsideIOR, eta2, smoothstep( 0.0, 0.03, thinFilmThickness ) );
		float sinTheta2Sq = pow2( outsideIOR / iridescenceIOR ) * ( 1.0 - pow2( cosTheta1 ) );
		float cosTheta2Sq = 1.0 - sinTheta2Sq;
		if ( cosTheta2Sq < 0.0 ) {
			return vec3( 1.0 );
		}
		float cosTheta2 = sqrt( cosTheta2Sq );
		float R0 = IorToFresnel0( iridescenceIOR, outsideIOR );
		float R12 = F_Schlick( R0, 1.0, cosTheta1 );
		float T121 = 1.0 - R12;
		float phi12 = 0.0;
		if ( iridescenceIOR < outsideIOR ) phi12 = PI;
		float phi21 = PI - phi12;
		vec3 baseIOR = Fresnel0ToIor( clamp( baseF0, 0.0, 0.9999 ) );		vec3 R1 = IorToFresnel0( baseIOR, iridescenceIOR );
		vec3 R23 = F_Schlick( R1, 1.0, cosTheta2 );
		vec3 phi23 = vec3( 0.0 );
		if ( baseIOR[ 0 ] < iridescenceIOR ) phi23[ 0 ] = PI;
		if ( baseIOR[ 1 ] < iridescenceIOR ) phi23[ 1 ] = PI;
		if ( baseIOR[ 2 ] < iridescenceIOR ) phi23[ 2 ] = PI;
		float OPD = 2.0 * iridescenceIOR * thinFilmThickness * cosTheta2;
		vec3 phi = vec3( phi21 ) + phi23;
		vec3 R123 = clamp( R12 * R23, 1e-5, 0.9999 );
		vec3 r123 = sqrt( R123 );
		vec3 Rs = pow2( T121 ) * R23 / ( vec3( 1.0 ) - R123 );
		vec3 C0 = R12 + Rs;
		I = C0;
		vec3 Cm = Rs - T121;
		for ( int m = 1; m <= 2; ++ m ) {
			Cm *= r123;
			vec3 Sm = 2.0 * evalSensitivity( float( m ) * OPD, float( m ) * phi );
			I += Cm * Sm;
		}
		return max( I, vec3( 0.0 ) );
	}
#endif`,pf=`#ifdef USE_BUMPMAP
	uniform sampler2D bumpMap;
	uniform float bumpScale;
	vec2 dHdxy_fwd() {
		vec2 dSTdx = dFdx( vBumpMapUv );
		vec2 dSTdy = dFdy( vBumpMapUv );
		float Hll = bumpScale * texture2D( bumpMap, vBumpMapUv ).x;
		float dBx = bumpScale * texture2D( bumpMap, vBumpMapUv + dSTdx ).x - Hll;
		float dBy = bumpScale * texture2D( bumpMap, vBumpMapUv + dSTdy ).x - Hll;
		return vec2( dBx, dBy );
	}
	vec3 perturbNormalArb( vec3 surf_pos, vec3 surf_norm, vec2 dHdxy, float faceDirection ) {
		vec3 vSigmaX = normalize( dFdx( surf_pos.xyz ) );
		vec3 vSigmaY = normalize( dFdy( surf_pos.xyz ) );
		vec3 vN = surf_norm;
		vec3 R1 = cross( vSigmaY, vN );
		vec3 R2 = cross( vN, vSigmaX );
		float fDet = dot( vSigmaX, R1 ) * faceDirection;
		vec3 vGrad = sign( fDet ) * ( dHdxy.x * R1 + dHdxy.y * R2 );
		return normalize( abs( fDet ) * surf_norm - vGrad );
	}
#endif`,mf=`#if NUM_CLIPPING_PLANES > 0
	vec4 plane;
	#ifdef ALPHA_TO_COVERAGE
		float distanceToPlane, distanceGradient;
		float clipOpacity = 1.0;
		#pragma unroll_loop_start
		for ( int i = 0; i < UNION_CLIPPING_PLANES; i ++ ) {
			plane = clippingPlanes[ i ];
			distanceToPlane = - dot( vClipPosition, plane.xyz ) + plane.w;
			distanceGradient = fwidth( distanceToPlane ) / 2.0;
			clipOpacity *= smoothstep( - distanceGradient, distanceGradient, distanceToPlane );
			if ( clipOpacity == 0.0 ) discard;
		}
		#pragma unroll_loop_end
		#if UNION_CLIPPING_PLANES < NUM_CLIPPING_PLANES
			float unionClipOpacity = 1.0;
			#pragma unroll_loop_start
			for ( int i = UNION_CLIPPING_PLANES; i < NUM_CLIPPING_PLANES; i ++ ) {
				plane = clippingPlanes[ i ];
				distanceToPlane = - dot( vClipPosition, plane.xyz ) + plane.w;
				distanceGradient = fwidth( distanceToPlane ) / 2.0;
				unionClipOpacity *= 1.0 - smoothstep( - distanceGradient, distanceGradient, distanceToPlane );
			}
			#pragma unroll_loop_end
			clipOpacity *= 1.0 - unionClipOpacity;
		#endif
		diffuseColor.a *= clipOpacity;
		if ( diffuseColor.a == 0.0 ) discard;
	#else
		#pragma unroll_loop_start
		for ( int i = 0; i < UNION_CLIPPING_PLANES; i ++ ) {
			plane = clippingPlanes[ i ];
			if ( dot( vClipPosition, plane.xyz ) > plane.w ) discard;
		}
		#pragma unroll_loop_end
		#if UNION_CLIPPING_PLANES < NUM_CLIPPING_PLANES
			bool clipped = true;
			#pragma unroll_loop_start
			for ( int i = UNION_CLIPPING_PLANES; i < NUM_CLIPPING_PLANES; i ++ ) {
				plane = clippingPlanes[ i ];
				clipped = ( dot( vClipPosition, plane.xyz ) > plane.w ) && clipped;
			}
			#pragma unroll_loop_end
			if ( clipped ) discard;
		#endif
	#endif
#endif`,gf=`#if NUM_CLIPPING_PLANES > 0
	varying vec3 vClipPosition;
	uniform vec4 clippingPlanes[ NUM_CLIPPING_PLANES ];
#endif`,vf=`#if NUM_CLIPPING_PLANES > 0
	varying vec3 vClipPosition;
#endif`,xf=`#if NUM_CLIPPING_PLANES > 0
	vClipPosition = - mvPosition.xyz;
#endif`,_f=`#if defined( USE_COLOR_ALPHA )
	diffuseColor *= vColor;
#elif defined( USE_COLOR )
	diffuseColor.rgb *= vColor;
#endif`,yf=`#if defined( USE_COLOR_ALPHA )
	varying vec4 vColor;
#elif defined( USE_COLOR )
	varying vec3 vColor;
#endif`,Mf=`#if defined( USE_COLOR_ALPHA )
	varying vec4 vColor;
#elif defined( USE_COLOR ) || defined( USE_INSTANCING_COLOR ) || defined( USE_BATCHING_COLOR )
	varying vec3 vColor;
#endif`,bf=`#if defined( USE_COLOR_ALPHA )
	vColor = vec4( 1.0 );
#elif defined( USE_COLOR ) || defined( USE_INSTANCING_COLOR ) || defined( USE_BATCHING_COLOR )
	vColor = vec3( 1.0 );
#endif
#ifdef USE_COLOR
	vColor *= color;
#endif
#ifdef USE_INSTANCING_COLOR
	vColor.xyz *= instanceColor.xyz;
#endif
#ifdef USE_BATCHING_COLOR
	vec3 batchingColor = getBatchingColor( getIndirectIndex( gl_DrawID ) );
	vColor.xyz *= batchingColor.xyz;
#endif`,wf=`#define PI 3.141592653589793
#define PI2 6.283185307179586
#define PI_HALF 1.5707963267948966
#define RECIPROCAL_PI 0.3183098861837907
#define RECIPROCAL_PI2 0.15915494309189535
#define EPSILON 1e-6
#ifndef saturate
#define saturate( a ) clamp( a, 0.0, 1.0 )
#endif
#define whiteComplement( a ) ( 1.0 - saturate( a ) )
float pow2( const in float x ) { return x*x; }
vec3 pow2( const in vec3 x ) { return x*x; }
float pow3( const in float x ) { return x*x*x; }
float pow4( const in float x ) { float x2 = x*x; return x2*x2; }
float max3( const in vec3 v ) { return max( max( v.x, v.y ), v.z ); }
float average( const in vec3 v ) { return dot( v, vec3( 0.3333333 ) ); }
highp float rand( const in vec2 uv ) {
	const highp float a = 12.9898, b = 78.233, c = 43758.5453;
	highp float dt = dot( uv.xy, vec2( a,b ) ), sn = mod( dt, PI );
	return fract( sin( sn ) * c );
}
#ifdef HIGH_PRECISION
	float precisionSafeLength( vec3 v ) { return length( v ); }
#else
	float precisionSafeLength( vec3 v ) {
		float maxComponent = max3( abs( v ) );
		return length( v / maxComponent ) * maxComponent;
	}
#endif
struct IncidentLight {
	vec3 color;
	vec3 direction;
	bool visible;
};
struct ReflectedLight {
	vec3 directDiffuse;
	vec3 directSpecular;
	vec3 indirectDiffuse;
	vec3 indirectSpecular;
};
#ifdef USE_ALPHAHASH
	varying vec3 vPosition;
#endif
vec3 transformDirection( in vec3 dir, in mat4 matrix ) {
	return normalize( ( matrix * vec4( dir, 0.0 ) ).xyz );
}
vec3 inverseTransformDirection( in vec3 dir, in mat4 matrix ) {
	return normalize( ( vec4( dir, 0.0 ) * matrix ).xyz );
}
mat3 transposeMat3( const in mat3 m ) {
	mat3 tmp;
	tmp[ 0 ] = vec3( m[ 0 ].x, m[ 1 ].x, m[ 2 ].x );
	tmp[ 1 ] = vec3( m[ 0 ].y, m[ 1 ].y, m[ 2 ].y );
	tmp[ 2 ] = vec3( m[ 0 ].z, m[ 1 ].z, m[ 2 ].z );
	return tmp;
}
bool isPerspectiveMatrix( mat4 m ) {
	return m[ 2 ][ 3 ] == - 1.0;
}
vec2 equirectUv( in vec3 dir ) {
	float u = atan( dir.z, dir.x ) * RECIPROCAL_PI2 + 0.5;
	float v = asin( clamp( dir.y, - 1.0, 1.0 ) ) * RECIPROCAL_PI + 0.5;
	return vec2( u, v );
}
vec3 BRDF_Lambert( const in vec3 diffuseColor ) {
	return RECIPROCAL_PI * diffuseColor;
}
vec3 F_Schlick( const in vec3 f0, const in float f90, const in float dotVH ) {
	float fresnel = exp2( ( - 5.55473 * dotVH - 6.98316 ) * dotVH );
	return f0 * ( 1.0 - fresnel ) + ( f90 * fresnel );
}
float F_Schlick( const in float f0, const in float f90, const in float dotVH ) {
	float fresnel = exp2( ( - 5.55473 * dotVH - 6.98316 ) * dotVH );
	return f0 * ( 1.0 - fresnel ) + ( f90 * fresnel );
} // validated`,Sf=`#ifdef ENVMAP_TYPE_CUBE_UV
	#define cubeUV_minMipLevel 4.0
	#define cubeUV_minTileSize 16.0
	float getFace( vec3 direction ) {
		vec3 absDirection = abs( direction );
		float face = - 1.0;
		if ( absDirection.x > absDirection.z ) {
			if ( absDirection.x > absDirection.y )
				face = direction.x > 0.0 ? 0.0 : 3.0;
			else
				face = direction.y > 0.0 ? 1.0 : 4.0;
		} else {
			if ( absDirection.z > absDirection.y )
				face = direction.z > 0.0 ? 2.0 : 5.0;
			else
				face = direction.y > 0.0 ? 1.0 : 4.0;
		}
		return face;
	}
	vec2 getUV( vec3 direction, float face ) {
		vec2 uv;
		if ( face == 0.0 ) {
			uv = vec2( direction.z, direction.y ) / abs( direction.x );
		} else if ( face == 1.0 ) {
			uv = vec2( - direction.x, - direction.z ) / abs( direction.y );
		} else if ( face == 2.0 ) {
			uv = vec2( - direction.x, direction.y ) / abs( direction.z );
		} else if ( face == 3.0 ) {
			uv = vec2( - direction.z, direction.y ) / abs( direction.x );
		} else if ( face == 4.0 ) {
			uv = vec2( - direction.x, direction.z ) / abs( direction.y );
		} else {
			uv = vec2( direction.x, direction.y ) / abs( direction.z );
		}
		return 0.5 * ( uv + 1.0 );
	}
	vec3 bilinearCubeUV( sampler2D envMap, vec3 direction, float mipInt ) {
		float face = getFace( direction );
		float filterInt = max( cubeUV_minMipLevel - mipInt, 0.0 );
		mipInt = max( mipInt, cubeUV_minMipLevel );
		float faceSize = exp2( mipInt );
		highp vec2 uv = getUV( direction, face ) * ( faceSize - 2.0 ) + 1.0;
		if ( face > 2.0 ) {
			uv.y += faceSize;
			face -= 3.0;
		}
		uv.x += face * faceSize;
		uv.x += filterInt * 3.0 * cubeUV_minTileSize;
		uv.y += 4.0 * ( exp2( CUBEUV_MAX_MIP ) - faceSize );
		uv.x *= CUBEUV_TEXEL_WIDTH;
		uv.y *= CUBEUV_TEXEL_HEIGHT;
		#ifdef texture2DGradEXT
			return texture2DGradEXT( envMap, uv, vec2( 0.0 ), vec2( 0.0 ) ).rgb;
		#else
			return texture2D( envMap, uv ).rgb;
		#endif
	}
	#define cubeUV_r0 1.0
	#define cubeUV_m0 - 2.0
	#define cubeUV_r1 0.8
	#define cubeUV_m1 - 1.0
	#define cubeUV_r4 0.4
	#define cubeUV_m4 2.0
	#define cubeUV_r5 0.305
	#define cubeUV_m5 3.0
	#define cubeUV_r6 0.21
	#define cubeUV_m6 4.0
	float roughnessToMip( float roughness ) {
		float mip = 0.0;
		if ( roughness >= cubeUV_r1 ) {
			mip = ( cubeUV_r0 - roughness ) * ( cubeUV_m1 - cubeUV_m0 ) / ( cubeUV_r0 - cubeUV_r1 ) + cubeUV_m0;
		} else if ( roughness >= cubeUV_r4 ) {
			mip = ( cubeUV_r1 - roughness ) * ( cubeUV_m4 - cubeUV_m1 ) / ( cubeUV_r1 - cubeUV_r4 ) + cubeUV_m1;
		} else if ( roughness >= cubeUV_r5 ) {
			mip = ( cubeUV_r4 - roughness ) * ( cubeUV_m5 - cubeUV_m4 ) / ( cubeUV_r4 - cubeUV_r5 ) + cubeUV_m4;
		} else if ( roughness >= cubeUV_r6 ) {
			mip = ( cubeUV_r5 - roughness ) * ( cubeUV_m6 - cubeUV_m5 ) / ( cubeUV_r5 - cubeUV_r6 ) + cubeUV_m5;
		} else {
			mip = - 2.0 * log2( 1.16 * roughness );		}
		return mip;
	}
	vec4 textureCubeUV( sampler2D envMap, vec3 sampleDir, float roughness ) {
		float mip = clamp( roughnessToMip( roughness ), cubeUV_m0, CUBEUV_MAX_MIP );
		float mipF = fract( mip );
		float mipInt = floor( mip );
		vec3 color0 = bilinearCubeUV( envMap, sampleDir, mipInt );
		if ( mipF == 0.0 ) {
			return vec4( color0, 1.0 );
		} else {
			vec3 color1 = bilinearCubeUV( envMap, sampleDir, mipInt + 1.0 );
			return vec4( mix( color0, color1, mipF ), 1.0 );
		}
	}
#endif`,Tf=`vec3 transformedNormal = objectNormal;
#ifdef USE_TANGENT
	vec3 transformedTangent = objectTangent;
#endif
#ifdef USE_BATCHING
	mat3 bm = mat3( batchingMatrix );
	transformedNormal /= vec3( dot( bm[ 0 ], bm[ 0 ] ), dot( bm[ 1 ], bm[ 1 ] ), dot( bm[ 2 ], bm[ 2 ] ) );
	transformedNormal = bm * transformedNormal;
	#ifdef USE_TANGENT
		transformedTangent = bm * transformedTangent;
	#endif
#endif
#ifdef USE_INSTANCING
	mat3 im = mat3( instanceMatrix );
	transformedNormal /= vec3( dot( im[ 0 ], im[ 0 ] ), dot( im[ 1 ], im[ 1 ] ), dot( im[ 2 ], im[ 2 ] ) );
	transformedNormal = im * transformedNormal;
	#ifdef USE_TANGENT
		transformedTangent = im * transformedTangent;
	#endif
#endif
transformedNormal = normalMatrix * transformedNormal;
#ifdef FLIP_SIDED
	transformedNormal = - transformedNormal;
#endif
#ifdef USE_TANGENT
	transformedTangent = ( modelViewMatrix * vec4( transformedTangent, 0.0 ) ).xyz;
	#ifdef FLIP_SIDED
		transformedTangent = - transformedTangent;
	#endif
#endif`,Ef=`#ifdef USE_DISPLACEMENTMAP
	uniform sampler2D displacementMap;
	uniform float displacementScale;
	uniform float displacementBias;
#endif`,Af=`#ifdef USE_DISPLACEMENTMAP
	transformed += normalize( objectNormal ) * ( texture2D( displacementMap, vDisplacementMapUv ).x * displacementScale + displacementBias );
#endif`,Cf=`#ifdef USE_EMISSIVEMAP
	vec4 emissiveColor = texture2D( emissiveMap, vEmissiveMapUv );
	totalEmissiveRadiance *= emissiveColor.rgb;
#endif`,Pf=`#ifdef USE_EMISSIVEMAP
	uniform sampler2D emissiveMap;
#endif`,Rf="gl_FragColor = linearToOutputTexel( gl_FragColor );",Df=`
const mat3 LINEAR_SRGB_TO_LINEAR_DISPLAY_P3 = mat3(
	vec3( 0.8224621, 0.177538, 0.0 ),
	vec3( 0.0331941, 0.9668058, 0.0 ),
	vec3( 0.0170827, 0.0723974, 0.9105199 )
);
const mat3 LINEAR_DISPLAY_P3_TO_LINEAR_SRGB = mat3(
	vec3( 1.2249401, - 0.2249404, 0.0 ),
	vec3( - 0.0420569, 1.0420571, 0.0 ),
	vec3( - 0.0196376, - 0.0786361, 1.0982735 )
);
vec4 LinearSRGBToLinearDisplayP3( in vec4 value ) {
	return vec4( value.rgb * LINEAR_SRGB_TO_LINEAR_DISPLAY_P3, value.a );
}
vec4 LinearDisplayP3ToLinearSRGB( in vec4 value ) {
	return vec4( value.rgb * LINEAR_DISPLAY_P3_TO_LINEAR_SRGB, value.a );
}
vec4 LinearTransferOETF( in vec4 value ) {
	return value;
}
vec4 sRGBTransferOETF( in vec4 value ) {
	return vec4( mix( pow( value.rgb, vec3( 0.41666 ) ) * 1.055 - vec3( 0.055 ), value.rgb * 12.92, vec3( lessThanEqual( value.rgb, vec3( 0.0031308 ) ) ) ), value.a );
}`,If=`#ifdef USE_ENVMAP
	#ifdef ENV_WORLDPOS
		vec3 cameraToFrag;
		if ( isOrthographic ) {
			cameraToFrag = normalize( vec3( - viewMatrix[ 0 ][ 2 ], - viewMatrix[ 1 ][ 2 ], - viewMatrix[ 2 ][ 2 ] ) );
		} else {
			cameraToFrag = normalize( vWorldPosition - cameraPosition );
		}
		vec3 worldNormal = inverseTransformDirection( normal, viewMatrix );
		#ifdef ENVMAP_MODE_REFLECTION
			vec3 reflectVec = reflect( cameraToFrag, worldNormal );
		#else
			vec3 reflectVec = refract( cameraToFrag, worldNormal, refractionRatio );
		#endif
	#else
		vec3 reflectVec = vReflect;
	#endif
	#ifdef ENVMAP_TYPE_CUBE
		vec4 envColor = textureCube( envMap, envMapRotation * vec3( flipEnvMap * reflectVec.x, reflectVec.yz ) );
	#else
		vec4 envColor = vec4( 0.0 );
	#endif
	#ifdef ENVMAP_BLENDING_MULTIPLY
		outgoingLight = mix( outgoingLight, outgoingLight * envColor.xyz, specularStrength * reflectivity );
	#elif defined( ENVMAP_BLENDING_MIX )
		outgoingLight = mix( outgoingLight, envColor.xyz, specularStrength * reflectivity );
	#elif defined( ENVMAP_BLENDING_ADD )
		outgoingLight += envColor.xyz * specularStrength * reflectivity;
	#endif
#endif`,Lf=`#ifdef USE_ENVMAP
	uniform float envMapIntensity;
	uniform float flipEnvMap;
	uniform mat3 envMapRotation;
	#ifdef ENVMAP_TYPE_CUBE
		uniform samplerCube envMap;
	#else
		uniform sampler2D envMap;
	#endif
	
#endif`,Nf=`#ifdef USE_ENVMAP
	uniform float reflectivity;
	#if defined( USE_BUMPMAP ) || defined( USE_NORMALMAP ) || defined( PHONG ) || defined( LAMBERT )
		#define ENV_WORLDPOS
	#endif
	#ifdef ENV_WORLDPOS
		varying vec3 vWorldPosition;
		uniform float refractionRatio;
	#else
		varying vec3 vReflect;
	#endif
#endif`,Uf=`#ifdef USE_ENVMAP
	#if defined( USE_BUMPMAP ) || defined( USE_NORMALMAP ) || defined( PHONG ) || defined( LAMBERT )
		#define ENV_WORLDPOS
	#endif
	#ifdef ENV_WORLDPOS
		
		varying vec3 vWorldPosition;
	#else
		varying vec3 vReflect;
		uniform float refractionRatio;
	#endif
#endif`,Of=`#ifdef USE_ENVMAP
	#ifdef ENV_WORLDPOS
		vWorldPosition = worldPosition.xyz;
	#else
		vec3 cameraToVertex;
		if ( isOrthographic ) {
			cameraToVertex = normalize( vec3( - viewMatrix[ 0 ][ 2 ], - viewMatrix[ 1 ][ 2 ], - viewMatrix[ 2 ][ 2 ] ) );
		} else {
			cameraToVertex = normalize( worldPosition.xyz - cameraPosition );
		}
		vec3 worldNormal = inverseTransformDirection( transformedNormal, viewMatrix );
		#ifdef ENVMAP_MODE_REFLECTION
			vReflect = reflect( cameraToVertex, worldNormal );
		#else
			vReflect = refract( cameraToVertex, worldNormal, refractionRatio );
		#endif
	#endif
#endif`,Ff=`#ifdef USE_FOG
	vFogDepth = - mvPosition.z;
#endif`,zf=`#ifdef USE_FOG
	varying float vFogDepth;
#endif`,kf=`#ifdef USE_FOG
	#ifdef FOG_EXP2
		float fogFactor = 1.0 - exp( - fogDensity * fogDensity * vFogDepth * vFogDepth );
	#else
		float fogFactor = smoothstep( fogNear, fogFar, vFogDepth );
	#endif
	gl_FragColor.rgb = mix( gl_FragColor.rgb, fogColor, fogFactor );
#endif`,Bf=`#ifdef USE_FOG
	uniform vec3 fogColor;
	varying float vFogDepth;
	#ifdef FOG_EXP2
		uniform float fogDensity;
	#else
		uniform float fogNear;
		uniform float fogFar;
	#endif
#endif`,Vf=`#ifdef USE_GRADIENTMAP
	uniform sampler2D gradientMap;
#endif
vec3 getGradientIrradiance( vec3 normal, vec3 lightDirection ) {
	float dotNL = dot( normal, lightDirection );
	vec2 coord = vec2( dotNL * 0.5 + 0.5, 0.0 );
	#ifdef USE_GRADIENTMAP
		return vec3( texture2D( gradientMap, coord ).r );
	#else
		vec2 fw = fwidth( coord ) * 0.5;
		return mix( vec3( 0.7 ), vec3( 1.0 ), smoothstep( 0.7 - fw.x, 0.7 + fw.x, coord.x ) );
	#endif
}`,Hf=`#ifdef USE_LIGHTMAP
	uniform sampler2D lightMap;
	uniform float lightMapIntensity;
#endif`,Gf=`LambertMaterial material;
material.diffuseColor = diffuseColor.rgb;
material.specularStrength = specularStrength;`,Wf=`varying vec3 vViewPosition;
struct LambertMaterial {
	vec3 diffuseColor;
	float specularStrength;
};
void RE_Direct_Lambert( const in IncidentLight directLight, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in LambertMaterial material, inout ReflectedLight reflectedLight ) {
	float dotNL = saturate( dot( geometryNormal, directLight.direction ) );
	vec3 irradiance = dotNL * directLight.color;
	reflectedLight.directDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
}
void RE_IndirectDiffuse_Lambert( const in vec3 irradiance, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in LambertMaterial material, inout ReflectedLight reflectedLight ) {
	reflectedLight.indirectDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
}
#define RE_Direct				RE_Direct_Lambert
#define RE_IndirectDiffuse		RE_IndirectDiffuse_Lambert`,Xf=`uniform bool receiveShadow;
uniform vec3 ambientLightColor;
#if defined( USE_LIGHT_PROBES )
	uniform vec3 lightProbe[ 9 ];
#endif
vec3 shGetIrradianceAt( in vec3 normal, in vec3 shCoefficients[ 9 ] ) {
	float x = normal.x, y = normal.y, z = normal.z;
	vec3 result = shCoefficients[ 0 ] * 0.886227;
	result += shCoefficients[ 1 ] * 2.0 * 0.511664 * y;
	result += shCoefficients[ 2 ] * 2.0 * 0.511664 * z;
	result += shCoefficients[ 3 ] * 2.0 * 0.511664 * x;
	result += shCoefficients[ 4 ] * 2.0 * 0.429043 * x * y;
	result += shCoefficients[ 5 ] * 2.0 * 0.429043 * y * z;
	result += shCoefficients[ 6 ] * ( 0.743125 * z * z - 0.247708 );
	result += shCoefficients[ 7 ] * 2.0 * 0.429043 * x * z;
	result += shCoefficients[ 8 ] * 0.429043 * ( x * x - y * y );
	return result;
}
vec3 getLightProbeIrradiance( const in vec3 lightProbe[ 9 ], const in vec3 normal ) {
	vec3 worldNormal = inverseTransformDirection( normal, viewMatrix );
	vec3 irradiance = shGetIrradianceAt( worldNormal, lightProbe );
	return irradiance;
}
vec3 getAmbientLightIrradiance( const in vec3 ambientLightColor ) {
	vec3 irradiance = ambientLightColor;
	return irradiance;
}
float getDistanceAttenuation( const in float lightDistance, const in float cutoffDistance, const in float decayExponent ) {
	float distanceFalloff = 1.0 / max( pow( lightDistance, decayExponent ), 0.01 );
	if ( cutoffDistance > 0.0 ) {
		distanceFalloff *= pow2( saturate( 1.0 - pow4( lightDistance / cutoffDistance ) ) );
	}
	return distanceFalloff;
}
float getSpotAttenuation( const in float coneCosine, const in float penumbraCosine, const in float angleCosine ) {
	return smoothstep( coneCosine, penumbraCosine, angleCosine );
}
#if NUM_DIR_LIGHTS > 0
	struct DirectionalLight {
		vec3 direction;
		vec3 color;
	};
	uniform DirectionalLight directionalLights[ NUM_DIR_LIGHTS ];
	void getDirectionalLightInfo( const in DirectionalLight directionalLight, out IncidentLight light ) {
		light.color = directionalLight.color;
		light.direction = directionalLight.direction;
		light.visible = true;
	}
#endif
#if NUM_POINT_LIGHTS > 0
	struct PointLight {
		vec3 position;
		vec3 color;
		float distance;
		float decay;
	};
	uniform PointLight pointLights[ NUM_POINT_LIGHTS ];
	void getPointLightInfo( const in PointLight pointLight, const in vec3 geometryPosition, out IncidentLight light ) {
		vec3 lVector = pointLight.position - geometryPosition;
		light.direction = normalize( lVector );
		float lightDistance = length( lVector );
		light.color = pointLight.color;
		light.color *= getDistanceAttenuation( lightDistance, pointLight.distance, pointLight.decay );
		light.visible = ( light.color != vec3( 0.0 ) );
	}
#endif
#if NUM_SPOT_LIGHTS > 0
	struct SpotLight {
		vec3 position;
		vec3 direction;
		vec3 color;
		float distance;
		float decay;
		float coneCos;
		float penumbraCos;
	};
	uniform SpotLight spotLights[ NUM_SPOT_LIGHTS ];
	void getSpotLightInfo( const in SpotLight spotLight, const in vec3 geometryPosition, out IncidentLight light ) {
		vec3 lVector = spotLight.position - geometryPosition;
		light.direction = normalize( lVector );
		float angleCos = dot( light.direction, spotLight.direction );
		float spotAttenuation = getSpotAttenuation( spotLight.coneCos, spotLight.penumbraCos, angleCos );
		if ( spotAttenuation > 0.0 ) {
			float lightDistance = length( lVector );
			light.color = spotLight.color * spotAttenuation;
			light.color *= getDistanceAttenuation( lightDistance, spotLight.distance, spotLight.decay );
			light.visible = ( light.color != vec3( 0.0 ) );
		} else {
			light.color = vec3( 0.0 );
			light.visible = false;
		}
	}
#endif
#if NUM_RECT_AREA_LIGHTS > 0
	struct RectAreaLight {
		vec3 color;
		vec3 position;
		vec3 halfWidth;
		vec3 halfHeight;
	};
	uniform sampler2D ltc_1;	uniform sampler2D ltc_2;
	uniform RectAreaLight rectAreaLights[ NUM_RECT_AREA_LIGHTS ];
#endif
#if NUM_HEMI_LIGHTS > 0
	struct HemisphereLight {
		vec3 direction;
		vec3 skyColor;
		vec3 groundColor;
	};
	uniform HemisphereLight hemisphereLights[ NUM_HEMI_LIGHTS ];
	vec3 getHemisphereLightIrradiance( const in HemisphereLight hemiLight, const in vec3 normal ) {
		float dotNL = dot( normal, hemiLight.direction );
		float hemiDiffuseWeight = 0.5 * dotNL + 0.5;
		vec3 irradiance = mix( hemiLight.groundColor, hemiLight.skyColor, hemiDiffuseWeight );
		return irradiance;
	}
#endif`,Yf=`#ifdef USE_ENVMAP
	vec3 getIBLIrradiance( const in vec3 normal ) {
		#ifdef ENVMAP_TYPE_CUBE_UV
			vec3 worldNormal = inverseTransformDirection( normal, viewMatrix );
			vec4 envMapColor = textureCubeUV( envMap, envMapRotation * worldNormal, 1.0 );
			return PI * envMapColor.rgb * envMapIntensity;
		#else
			return vec3( 0.0 );
		#endif
	}
	vec3 getIBLRadiance( const in vec3 viewDir, const in vec3 normal, const in float roughness ) {
		#ifdef ENVMAP_TYPE_CUBE_UV
			vec3 reflectVec = reflect( - viewDir, normal );
			reflectVec = normalize( mix( reflectVec, normal, roughness * roughness) );
			reflectVec = inverseTransformDirection( reflectVec, viewMatrix );
			vec4 envMapColor = textureCubeUV( envMap, envMapRotation * reflectVec, roughness );
			return envMapColor.rgb * envMapIntensity;
		#else
			return vec3( 0.0 );
		#endif
	}
	#ifdef USE_ANISOTROPY
		vec3 getIBLAnisotropyRadiance( const in vec3 viewDir, const in vec3 normal, const in float roughness, const in vec3 bitangent, const in float anisotropy ) {
			#ifdef ENVMAP_TYPE_CUBE_UV
				vec3 bentNormal = cross( bitangent, viewDir );
				bentNormal = normalize( cross( bentNormal, bitangent ) );
				bentNormal = normalize( mix( bentNormal, normal, pow2( pow2( 1.0 - anisotropy * ( 1.0 - roughness ) ) ) ) );
				return getIBLRadiance( viewDir, bentNormal, roughness );
			#else
				return vec3( 0.0 );
			#endif
		}
	#endif
#endif`,qf=`ToonMaterial material;
material.diffuseColor = diffuseColor.rgb;`,jf=`varying vec3 vViewPosition;
struct ToonMaterial {
	vec3 diffuseColor;
};
void RE_Direct_Toon( const in IncidentLight directLight, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in ToonMaterial material, inout ReflectedLight reflectedLight ) {
	vec3 irradiance = getGradientIrradiance( geometryNormal, directLight.direction ) * directLight.color;
	reflectedLight.directDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
}
void RE_IndirectDiffuse_Toon( const in vec3 irradiance, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in ToonMaterial material, inout ReflectedLight reflectedLight ) {
	reflectedLight.indirectDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
}
#define RE_Direct				RE_Direct_Toon
#define RE_IndirectDiffuse		RE_IndirectDiffuse_Toon`,Kf=`BlinnPhongMaterial material;
material.diffuseColor = diffuseColor.rgb;
material.specularColor = specular;
material.specularShininess = shininess;
material.specularStrength = specularStrength;`,Zf=`varying vec3 vViewPosition;
struct BlinnPhongMaterial {
	vec3 diffuseColor;
	vec3 specularColor;
	float specularShininess;
	float specularStrength;
};
void RE_Direct_BlinnPhong( const in IncidentLight directLight, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in BlinnPhongMaterial material, inout ReflectedLight reflectedLight ) {
	float dotNL = saturate( dot( geometryNormal, directLight.direction ) );
	vec3 irradiance = dotNL * directLight.color;
	reflectedLight.directDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
	reflectedLight.directSpecular += irradiance * BRDF_BlinnPhong( directLight.direction, geometryViewDir, geometryNormal, material.specularColor, material.specularShininess ) * material.specularStrength;
}
void RE_IndirectDiffuse_BlinnPhong( const in vec3 irradiance, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in BlinnPhongMaterial material, inout ReflectedLight reflectedLight ) {
	reflectedLight.indirectDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
}
#define RE_Direct				RE_Direct_BlinnPhong
#define RE_IndirectDiffuse		RE_IndirectDiffuse_BlinnPhong`,Jf=`PhysicalMaterial material;
material.diffuseColor = diffuseColor.rgb * ( 1.0 - metalnessFactor );
vec3 dxy = max( abs( dFdx( nonPerturbedNormal ) ), abs( dFdy( nonPerturbedNormal ) ) );
float geometryRoughness = max( max( dxy.x, dxy.y ), dxy.z );
material.roughness = max( roughnessFactor, 0.0525 );material.roughness += geometryRoughness;
material.roughness = min( material.roughness, 1.0 );
#ifdef IOR
	material.ior = ior;
	#ifdef USE_SPECULAR
		float specularIntensityFactor = specularIntensity;
		vec3 specularColorFactor = specularColor;
		#ifdef USE_SPECULAR_COLORMAP
			specularColorFactor *= texture2D( specularColorMap, vSpecularColorMapUv ).rgb;
		#endif
		#ifdef USE_SPECULAR_INTENSITYMAP
			specularIntensityFactor *= texture2D( specularIntensityMap, vSpecularIntensityMapUv ).a;
		#endif
		material.specularF90 = mix( specularIntensityFactor, 1.0, metalnessFactor );
	#else
		float specularIntensityFactor = 1.0;
		vec3 specularColorFactor = vec3( 1.0 );
		material.specularF90 = 1.0;
	#endif
	material.specularColor = mix( min( pow2( ( material.ior - 1.0 ) / ( material.ior + 1.0 ) ) * specularColorFactor, vec3( 1.0 ) ) * specularIntensityFactor, diffuseColor.rgb, metalnessFactor );
#else
	material.specularColor = mix( vec3( 0.04 ), diffuseColor.rgb, metalnessFactor );
	material.specularF90 = 1.0;
#endif
#ifdef USE_CLEARCOAT
	material.clearcoat = clearcoat;
	material.clearcoatRoughness = clearcoatRoughness;
	material.clearcoatF0 = vec3( 0.04 );
	material.clearcoatF90 = 1.0;
	#ifdef USE_CLEARCOATMAP
		material.clearcoat *= texture2D( clearcoatMap, vClearcoatMapUv ).x;
	#endif
	#ifdef USE_CLEARCOAT_ROUGHNESSMAP
		material.clearcoatRoughness *= texture2D( clearcoatRoughnessMap, vClearcoatRoughnessMapUv ).y;
	#endif
	material.clearcoat = saturate( material.clearcoat );	material.clearcoatRoughness = max( material.clearcoatRoughness, 0.0525 );
	material.clearcoatRoughness += geometryRoughness;
	material.clearcoatRoughness = min( material.clearcoatRoughness, 1.0 );
#endif
#ifdef USE_DISPERSION
	material.dispersion = dispersion;
#endif
#ifdef USE_IRIDESCENCE
	material.iridescence = iridescence;
	material.iridescenceIOR = iridescenceIOR;
	#ifdef USE_IRIDESCENCEMAP
		material.iridescence *= texture2D( iridescenceMap, vIridescenceMapUv ).r;
	#endif
	#ifdef USE_IRIDESCENCE_THICKNESSMAP
		material.iridescenceThickness = (iridescenceThicknessMaximum - iridescenceThicknessMinimum) * texture2D( iridescenceThicknessMap, vIridescenceThicknessMapUv ).g + iridescenceThicknessMinimum;
	#else
		material.iridescenceThickness = iridescenceThicknessMaximum;
	#endif
#endif
#ifdef USE_SHEEN
	material.sheenColor = sheenColor;
	#ifdef USE_SHEEN_COLORMAP
		material.sheenColor *= texture2D( sheenColorMap, vSheenColorMapUv ).rgb;
	#endif
	material.sheenRoughness = clamp( sheenRoughness, 0.07, 1.0 );
	#ifdef USE_SHEEN_ROUGHNESSMAP
		material.sheenRoughness *= texture2D( sheenRoughnessMap, vSheenRoughnessMapUv ).a;
	#endif
#endif
#ifdef USE_ANISOTROPY
	#ifdef USE_ANISOTROPYMAP
		mat2 anisotropyMat = mat2( anisotropyVector.x, anisotropyVector.y, - anisotropyVector.y, anisotropyVector.x );
		vec3 anisotropyPolar = texture2D( anisotropyMap, vAnisotropyMapUv ).rgb;
		vec2 anisotropyV = anisotropyMat * normalize( 2.0 * anisotropyPolar.rg - vec2( 1.0 ) ) * anisotropyPolar.b;
	#else
		vec2 anisotropyV = anisotropyVector;
	#endif
	material.anisotropy = length( anisotropyV );
	if( material.anisotropy == 0.0 ) {
		anisotropyV = vec2( 1.0, 0.0 );
	} else {
		anisotropyV /= material.anisotropy;
		material.anisotropy = saturate( material.anisotropy );
	}
	material.alphaT = mix( pow2( material.roughness ), 1.0, pow2( material.anisotropy ) );
	material.anisotropyT = tbn[ 0 ] * anisotropyV.x + tbn[ 1 ] * anisotropyV.y;
	material.anisotropyB = tbn[ 1 ] * anisotropyV.x - tbn[ 0 ] * anisotropyV.y;
#endif`,$f=`struct PhysicalMaterial {
	vec3 diffuseColor;
	float roughness;
	vec3 specularColor;
	float specularF90;
	float dispersion;
	#ifdef USE_CLEARCOAT
		float clearcoat;
		float clearcoatRoughness;
		vec3 clearcoatF0;
		float clearcoatF90;
	#endif
	#ifdef USE_IRIDESCENCE
		float iridescence;
		float iridescenceIOR;
		float iridescenceThickness;
		vec3 iridescenceFresnel;
		vec3 iridescenceF0;
	#endif
	#ifdef USE_SHEEN
		vec3 sheenColor;
		float sheenRoughness;
	#endif
	#ifdef IOR
		float ior;
	#endif
	#ifdef USE_TRANSMISSION
		float transmission;
		float transmissionAlpha;
		float thickness;
		float attenuationDistance;
		vec3 attenuationColor;
	#endif
	#ifdef USE_ANISOTROPY
		float anisotropy;
		float alphaT;
		vec3 anisotropyT;
		vec3 anisotropyB;
	#endif
};
vec3 clearcoatSpecularDirect = vec3( 0.0 );
vec3 clearcoatSpecularIndirect = vec3( 0.0 );
vec3 sheenSpecularDirect = vec3( 0.0 );
vec3 sheenSpecularIndirect = vec3(0.0 );
vec3 Schlick_to_F0( const in vec3 f, const in float f90, const in float dotVH ) {
    float x = clamp( 1.0 - dotVH, 0.0, 1.0 );
    float x2 = x * x;
    float x5 = clamp( x * x2 * x2, 0.0, 0.9999 );
    return ( f - vec3( f90 ) * x5 ) / ( 1.0 - x5 );
}
float V_GGX_SmithCorrelated( const in float alpha, const in float dotNL, const in float dotNV ) {
	float a2 = pow2( alpha );
	float gv = dotNL * sqrt( a2 + ( 1.0 - a2 ) * pow2( dotNV ) );
	float gl = dotNV * sqrt( a2 + ( 1.0 - a2 ) * pow2( dotNL ) );
	return 0.5 / max( gv + gl, EPSILON );
}
float D_GGX( const in float alpha, const in float dotNH ) {
	float a2 = pow2( alpha );
	float denom = pow2( dotNH ) * ( a2 - 1.0 ) + 1.0;
	return RECIPROCAL_PI * a2 / pow2( denom );
}
#ifdef USE_ANISOTROPY
	float V_GGX_SmithCorrelated_Anisotropic( const in float alphaT, const in float alphaB, const in float dotTV, const in float dotBV, const in float dotTL, const in float dotBL, const in float dotNV, const in float dotNL ) {
		float gv = dotNL * length( vec3( alphaT * dotTV, alphaB * dotBV, dotNV ) );
		float gl = dotNV * length( vec3( alphaT * dotTL, alphaB * dotBL, dotNL ) );
		float v = 0.5 / ( gv + gl );
		return saturate(v);
	}
	float D_GGX_Anisotropic( const in float alphaT, const in float alphaB, const in float dotNH, const in float dotTH, const in float dotBH ) {
		float a2 = alphaT * alphaB;
		highp vec3 v = vec3( alphaB * dotTH, alphaT * dotBH, a2 * dotNH );
		highp float v2 = dot( v, v );
		float w2 = a2 / v2;
		return RECIPROCAL_PI * a2 * pow2 ( w2 );
	}
#endif
#ifdef USE_CLEARCOAT
	vec3 BRDF_GGX_Clearcoat( const in vec3 lightDir, const in vec3 viewDir, const in vec3 normal, const in PhysicalMaterial material) {
		vec3 f0 = material.clearcoatF0;
		float f90 = material.clearcoatF90;
		float roughness = material.clearcoatRoughness;
		float alpha = pow2( roughness );
		vec3 halfDir = normalize( lightDir + viewDir );
		float dotNL = saturate( dot( normal, lightDir ) );
		float dotNV = saturate( dot( normal, viewDir ) );
		float dotNH = saturate( dot( normal, halfDir ) );
		float dotVH = saturate( dot( viewDir, halfDir ) );
		vec3 F = F_Schlick( f0, f90, dotVH );
		float V = V_GGX_SmithCorrelated( alpha, dotNL, dotNV );
		float D = D_GGX( alpha, dotNH );
		return F * ( V * D );
	}
#endif
vec3 BRDF_GGX( const in vec3 lightDir, const in vec3 viewDir, const in vec3 normal, const in PhysicalMaterial material ) {
	vec3 f0 = material.specularColor;
	float f90 = material.specularF90;
	float roughness = material.roughness;
	float alpha = pow2( roughness );
	vec3 halfDir = normalize( lightDir + viewDir );
	float dotNL = saturate( dot( normal, lightDir ) );
	float dotNV = saturate( dot( normal, viewDir ) );
	float dotNH = saturate( dot( normal, halfDir ) );
	float dotVH = saturate( dot( viewDir, halfDir ) );
	vec3 F = F_Schlick( f0, f90, dotVH );
	#ifdef USE_IRIDESCENCE
		F = mix( F, material.iridescenceFresnel, material.iridescence );
	#endif
	#ifdef USE_ANISOTROPY
		float dotTL = dot( material.anisotropyT, lightDir );
		float dotTV = dot( material.anisotropyT, viewDir );
		float dotTH = dot( material.anisotropyT, halfDir );
		float dotBL = dot( material.anisotropyB, lightDir );
		float dotBV = dot( material.anisotropyB, viewDir );
		float dotBH = dot( material.anisotropyB, halfDir );
		float V = V_GGX_SmithCorrelated_Anisotropic( material.alphaT, alpha, dotTV, dotBV, dotTL, dotBL, dotNV, dotNL );
		float D = D_GGX_Anisotropic( material.alphaT, alpha, dotNH, dotTH, dotBH );
	#else
		float V = V_GGX_SmithCorrelated( alpha, dotNL, dotNV );
		float D = D_GGX( alpha, dotNH );
	#endif
	return F * ( V * D );
}
vec2 LTC_Uv( const in vec3 N, const in vec3 V, const in float roughness ) {
	const float LUT_SIZE = 64.0;
	const float LUT_SCALE = ( LUT_SIZE - 1.0 ) / LUT_SIZE;
	const float LUT_BIAS = 0.5 / LUT_SIZE;
	float dotNV = saturate( dot( N, V ) );
	vec2 uv = vec2( roughness, sqrt( 1.0 - dotNV ) );
	uv = uv * LUT_SCALE + LUT_BIAS;
	return uv;
}
float LTC_ClippedSphereFormFactor( const in vec3 f ) {
	float l = length( f );
	return max( ( l * l + f.z ) / ( l + 1.0 ), 0.0 );
}
vec3 LTC_EdgeVectorFormFactor( const in vec3 v1, const in vec3 v2 ) {
	float x = dot( v1, v2 );
	float y = abs( x );
	float a = 0.8543985 + ( 0.4965155 + 0.0145206 * y ) * y;
	float b = 3.4175940 + ( 4.1616724 + y ) * y;
	float v = a / b;
	float theta_sintheta = ( x > 0.0 ) ? v : 0.5 * inversesqrt( max( 1.0 - x * x, 1e-7 ) ) - v;
	return cross( v1, v2 ) * theta_sintheta;
}
vec3 LTC_Evaluate( const in vec3 N, const in vec3 V, const in vec3 P, const in mat3 mInv, const in vec3 rectCoords[ 4 ] ) {
	vec3 v1 = rectCoords[ 1 ] - rectCoords[ 0 ];
	vec3 v2 = rectCoords[ 3 ] - rectCoords[ 0 ];
	vec3 lightNormal = cross( v1, v2 );
	if( dot( lightNormal, P - rectCoords[ 0 ] ) < 0.0 ) return vec3( 0.0 );
	vec3 T1, T2;
	T1 = normalize( V - N * dot( V, N ) );
	T2 = - cross( N, T1 );
	mat3 mat = mInv * transposeMat3( mat3( T1, T2, N ) );
	vec3 coords[ 4 ];
	coords[ 0 ] = mat * ( rectCoords[ 0 ] - P );
	coords[ 1 ] = mat * ( rectCoords[ 1 ] - P );
	coords[ 2 ] = mat * ( rectCoords[ 2 ] - P );
	coords[ 3 ] = mat * ( rectCoords[ 3 ] - P );
	coords[ 0 ] = normalize( coords[ 0 ] );
	coords[ 1 ] = normalize( coords[ 1 ] );
	coords[ 2 ] = normalize( coords[ 2 ] );
	coords[ 3 ] = normalize( coords[ 3 ] );
	vec3 vectorFormFactor = vec3( 0.0 );
	vectorFormFactor += LTC_EdgeVectorFormFactor( coords[ 0 ], coords[ 1 ] );
	vectorFormFactor += LTC_EdgeVectorFormFactor( coords[ 1 ], coords[ 2 ] );
	vectorFormFactor += LTC_EdgeVectorFormFactor( coords[ 2 ], coords[ 3 ] );
	vectorFormFactor += LTC_EdgeVectorFormFactor( coords[ 3 ], coords[ 0 ] );
	float result = LTC_ClippedSphereFormFactor( vectorFormFactor );
	return vec3( result );
}
#if defined( USE_SHEEN )
float D_Charlie( float roughness, float dotNH ) {
	float alpha = pow2( roughness );
	float invAlpha = 1.0 / alpha;
	float cos2h = dotNH * dotNH;
	float sin2h = max( 1.0 - cos2h, 0.0078125 );
	return ( 2.0 + invAlpha ) * pow( sin2h, invAlpha * 0.5 ) / ( 2.0 * PI );
}
float V_Neubelt( float dotNV, float dotNL ) {
	return saturate( 1.0 / ( 4.0 * ( dotNL + dotNV - dotNL * dotNV ) ) );
}
vec3 BRDF_Sheen( const in vec3 lightDir, const in vec3 viewDir, const in vec3 normal, vec3 sheenColor, const in float sheenRoughness ) {
	vec3 halfDir = normalize( lightDir + viewDir );
	float dotNL = saturate( dot( normal, lightDir ) );
	float dotNV = saturate( dot( normal, viewDir ) );
	float dotNH = saturate( dot( normal, halfDir ) );
	float D = D_Charlie( sheenRoughness, dotNH );
	float V = V_Neubelt( dotNV, dotNL );
	return sheenColor * ( D * V );
}
#endif
float IBLSheenBRDF( const in vec3 normal, const in vec3 viewDir, const in float roughness ) {
	float dotNV = saturate( dot( normal, viewDir ) );
	float r2 = roughness * roughness;
	float a = roughness < 0.25 ? -339.2 * r2 + 161.4 * roughness - 25.9 : -8.48 * r2 + 14.3 * roughness - 9.95;
	float b = roughness < 0.25 ? 44.0 * r2 - 23.7 * roughness + 3.26 : 1.97 * r2 - 3.27 * roughness + 0.72;
	float DG = exp( a * dotNV + b ) + ( roughness < 0.25 ? 0.0 : 0.1 * ( roughness - 0.25 ) );
	return saturate( DG * RECIPROCAL_PI );
}
vec2 DFGApprox( const in vec3 normal, const in vec3 viewDir, const in float roughness ) {
	float dotNV = saturate( dot( normal, viewDir ) );
	const vec4 c0 = vec4( - 1, - 0.0275, - 0.572, 0.022 );
	const vec4 c1 = vec4( 1, 0.0425, 1.04, - 0.04 );
	vec4 r = roughness * c0 + c1;
	float a004 = min( r.x * r.x, exp2( - 9.28 * dotNV ) ) * r.x + r.y;
	vec2 fab = vec2( - 1.04, 1.04 ) * a004 + r.zw;
	return fab;
}
vec3 EnvironmentBRDF( const in vec3 normal, const in vec3 viewDir, const in vec3 specularColor, const in float specularF90, const in float roughness ) {
	vec2 fab = DFGApprox( normal, viewDir, roughness );
	return specularColor * fab.x + specularF90 * fab.y;
}
#ifdef USE_IRIDESCENCE
void computeMultiscatteringIridescence( const in vec3 normal, const in vec3 viewDir, const in vec3 specularColor, const in float specularF90, const in float iridescence, const in vec3 iridescenceF0, const in float roughness, inout vec3 singleScatter, inout vec3 multiScatter ) {
#else
void computeMultiscattering( const in vec3 normal, const in vec3 viewDir, const in vec3 specularColor, const in float specularF90, const in float roughness, inout vec3 singleScatter, inout vec3 multiScatter ) {
#endif
	vec2 fab = DFGApprox( normal, viewDir, roughness );
	#ifdef USE_IRIDESCENCE
		vec3 Fr = mix( specularColor, iridescenceF0, iridescence );
	#else
		vec3 Fr = specularColor;
	#endif
	vec3 FssEss = Fr * fab.x + specularF90 * fab.y;
	float Ess = fab.x + fab.y;
	float Ems = 1.0 - Ess;
	vec3 Favg = Fr + ( 1.0 - Fr ) * 0.047619;	vec3 Fms = FssEss * Favg / ( 1.0 - Ems * Favg );
	singleScatter += FssEss;
	multiScatter += Fms * Ems;
}
#if NUM_RECT_AREA_LIGHTS > 0
	void RE_Direct_RectArea_Physical( const in RectAreaLight rectAreaLight, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in PhysicalMaterial material, inout ReflectedLight reflectedLight ) {
		vec3 normal = geometryNormal;
		vec3 viewDir = geometryViewDir;
		vec3 position = geometryPosition;
		vec3 lightPos = rectAreaLight.position;
		vec3 halfWidth = rectAreaLight.halfWidth;
		vec3 halfHeight = rectAreaLight.halfHeight;
		vec3 lightColor = rectAreaLight.color;
		float roughness = material.roughness;
		vec3 rectCoords[ 4 ];
		rectCoords[ 0 ] = lightPos + halfWidth - halfHeight;		rectCoords[ 1 ] = lightPos - halfWidth - halfHeight;
		rectCoords[ 2 ] = lightPos - halfWidth + halfHeight;
		rectCoords[ 3 ] = lightPos + halfWidth + halfHeight;
		vec2 uv = LTC_Uv( normal, viewDir, roughness );
		vec4 t1 = texture2D( ltc_1, uv );
		vec4 t2 = texture2D( ltc_2, uv );
		mat3 mInv = mat3(
			vec3( t1.x, 0, t1.y ),
			vec3(    0, 1,    0 ),
			vec3( t1.z, 0, t1.w )
		);
		vec3 fresnel = ( material.specularColor * t2.x + ( vec3( 1.0 ) - material.specularColor ) * t2.y );
		reflectedLight.directSpecular += lightColor * fresnel * LTC_Evaluate( normal, viewDir, position, mInv, rectCoords );
		reflectedLight.directDiffuse += lightColor * material.diffuseColor * LTC_Evaluate( normal, viewDir, position, mat3( 1.0 ), rectCoords );
	}
#endif
void RE_Direct_Physical( const in IncidentLight directLight, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in PhysicalMaterial material, inout ReflectedLight reflectedLight ) {
	float dotNL = saturate( dot( geometryNormal, directLight.direction ) );
	vec3 irradiance = dotNL * directLight.color;
	#ifdef USE_CLEARCOAT
		float dotNLcc = saturate( dot( geometryClearcoatNormal, directLight.direction ) );
		vec3 ccIrradiance = dotNLcc * directLight.color;
		clearcoatSpecularDirect += ccIrradiance * BRDF_GGX_Clearcoat( directLight.direction, geometryViewDir, geometryClearcoatNormal, material );
	#endif
	#ifdef USE_SHEEN
		sheenSpecularDirect += irradiance * BRDF_Sheen( directLight.direction, geometryViewDir, geometryNormal, material.sheenColor, material.sheenRoughness );
	#endif
	reflectedLight.directSpecular += irradiance * BRDF_GGX( directLight.direction, geometryViewDir, geometryNormal, material );
	reflectedLight.directDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
}
void RE_IndirectDiffuse_Physical( const in vec3 irradiance, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in PhysicalMaterial material, inout ReflectedLight reflectedLight ) {
	reflectedLight.indirectDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
}
void RE_IndirectSpecular_Physical( const in vec3 radiance, const in vec3 irradiance, const in vec3 clearcoatRadiance, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in PhysicalMaterial material, inout ReflectedLight reflectedLight) {
	#ifdef USE_CLEARCOAT
		clearcoatSpecularIndirect += clearcoatRadiance * EnvironmentBRDF( geometryClearcoatNormal, geometryViewDir, material.clearcoatF0, material.clearcoatF90, material.clearcoatRoughness );
	#endif
	#ifdef USE_SHEEN
		sheenSpecularIndirect += irradiance * material.sheenColor * IBLSheenBRDF( geometryNormal, geometryViewDir, material.sheenRoughness );
	#endif
	vec3 singleScattering = vec3( 0.0 );
	vec3 multiScattering = vec3( 0.0 );
	vec3 cosineWeightedIrradiance = irradiance * RECIPROCAL_PI;
	#ifdef USE_IRIDESCENCE
		computeMultiscatteringIridescence( geometryNormal, geometryViewDir, material.specularColor, material.specularF90, material.iridescence, material.iridescenceFresnel, material.roughness, singleScattering, multiScattering );
	#else
		computeMultiscattering( geometryNormal, geometryViewDir, material.specularColor, material.specularF90, material.roughness, singleScattering, multiScattering );
	#endif
	vec3 totalScattering = singleScattering + multiScattering;
	vec3 diffuse = material.diffuseColor * ( 1.0 - max( max( totalScattering.r, totalScattering.g ), totalScattering.b ) );
	reflectedLight.indirectSpecular += radiance * singleScattering;
	reflectedLight.indirectSpecular += multiScattering * cosineWeightedIrradiance;
	reflectedLight.indirectDiffuse += diffuse * cosineWeightedIrradiance;
}
#define RE_Direct				RE_Direct_Physical
#define RE_Direct_RectArea		RE_Direct_RectArea_Physical
#define RE_IndirectDiffuse		RE_IndirectDiffuse_Physical
#define RE_IndirectSpecular		RE_IndirectSpecular_Physical
float computeSpecularOcclusion( const in float dotNV, const in float ambientOcclusion, const in float roughness ) {
	return saturate( pow( dotNV + ambientOcclusion, exp2( - 16.0 * roughness - 1.0 ) ) - 1.0 + ambientOcclusion );
}`,Qf=`
vec3 geometryPosition = - vViewPosition;
vec3 geometryNormal = normal;
vec3 geometryViewDir = ( isOrthographic ) ? vec3( 0, 0, 1 ) : normalize( vViewPosition );
vec3 geometryClearcoatNormal = vec3( 0.0 );
#ifdef USE_CLEARCOAT
	geometryClearcoatNormal = clearcoatNormal;
#endif
#ifdef USE_IRIDESCENCE
	float dotNVi = saturate( dot( normal, geometryViewDir ) );
	if ( material.iridescenceThickness == 0.0 ) {
		material.iridescence = 0.0;
	} else {
		material.iridescence = saturate( material.iridescence );
	}
	if ( material.iridescence > 0.0 ) {
		material.iridescenceFresnel = evalIridescence( 1.0, material.iridescenceIOR, dotNVi, material.iridescenceThickness, material.specularColor );
		material.iridescenceF0 = Schlick_to_F0( material.iridescenceFresnel, 1.0, dotNVi );
	}
#endif
IncidentLight directLight;
#if ( NUM_POINT_LIGHTS > 0 ) && defined( RE_Direct )
	PointLight pointLight;
	#if defined( USE_SHADOWMAP ) && NUM_POINT_LIGHT_SHADOWS > 0
	PointLightShadow pointLightShadow;
	#endif
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_POINT_LIGHTS; i ++ ) {
		pointLight = pointLights[ i ];
		getPointLightInfo( pointLight, geometryPosition, directLight );
		#if defined( USE_SHADOWMAP ) && ( UNROLLED_LOOP_INDEX < NUM_POINT_LIGHT_SHADOWS )
		pointLightShadow = pointLightShadows[ i ];
		directLight.color *= ( directLight.visible && receiveShadow ) ? getPointShadow( pointShadowMap[ i ], pointLightShadow.shadowMapSize, pointLightShadow.shadowIntensity, pointLightShadow.shadowBias, pointLightShadow.shadowRadius, vPointShadowCoord[ i ], pointLightShadow.shadowCameraNear, pointLightShadow.shadowCameraFar ) : 1.0;
		#endif
		RE_Direct( directLight, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
	}
	#pragma unroll_loop_end
#endif
#if ( NUM_SPOT_LIGHTS > 0 ) && defined( RE_Direct )
	SpotLight spotLight;
	vec4 spotColor;
	vec3 spotLightCoord;
	bool inSpotLightMap;
	#if defined( USE_SHADOWMAP ) && NUM_SPOT_LIGHT_SHADOWS > 0
	SpotLightShadow spotLightShadow;
	#endif
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_SPOT_LIGHTS; i ++ ) {
		spotLight = spotLights[ i ];
		getSpotLightInfo( spotLight, geometryPosition, directLight );
		#if ( UNROLLED_LOOP_INDEX < NUM_SPOT_LIGHT_SHADOWS_WITH_MAPS )
		#define SPOT_LIGHT_MAP_INDEX UNROLLED_LOOP_INDEX
		#elif ( UNROLLED_LOOP_INDEX < NUM_SPOT_LIGHT_SHADOWS )
		#define SPOT_LIGHT_MAP_INDEX NUM_SPOT_LIGHT_MAPS
		#else
		#define SPOT_LIGHT_MAP_INDEX ( UNROLLED_LOOP_INDEX - NUM_SPOT_LIGHT_SHADOWS + NUM_SPOT_LIGHT_SHADOWS_WITH_MAPS )
		#endif
		#if ( SPOT_LIGHT_MAP_INDEX < NUM_SPOT_LIGHT_MAPS )
			spotLightCoord = vSpotLightCoord[ i ].xyz / vSpotLightCoord[ i ].w;
			inSpotLightMap = all( lessThan( abs( spotLightCoord * 2. - 1. ), vec3( 1.0 ) ) );
			spotColor = texture2D( spotLightMap[ SPOT_LIGHT_MAP_INDEX ], spotLightCoord.xy );
			directLight.color = inSpotLightMap ? directLight.color * spotColor.rgb : directLight.color;
		#endif
		#undef SPOT_LIGHT_MAP_INDEX
		#if defined( USE_SHADOWMAP ) && ( UNROLLED_LOOP_INDEX < NUM_SPOT_LIGHT_SHADOWS )
		spotLightShadow = spotLightShadows[ i ];
		directLight.color *= ( directLight.visible && receiveShadow ) ? getShadow( spotShadowMap[ i ], spotLightShadow.shadowMapSize, spotLightShadow.shadowIntensity, spotLightShadow.shadowBias, spotLightShadow.shadowRadius, vSpotLightCoord[ i ] ) : 1.0;
		#endif
		RE_Direct( directLight, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
	}
	#pragma unroll_loop_end
#endif
#if ( NUM_DIR_LIGHTS > 0 ) && defined( RE_Direct )
	DirectionalLight directionalLight;
	#if defined( USE_SHADOWMAP ) && NUM_DIR_LIGHT_SHADOWS > 0
	DirectionalLightShadow directionalLightShadow;
	#endif
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_DIR_LIGHTS; i ++ ) {
		directionalLight = directionalLights[ i ];
		getDirectionalLightInfo( directionalLight, directLight );
		#if defined( USE_SHADOWMAP ) && ( UNROLLED_LOOP_INDEX < NUM_DIR_LIGHT_SHADOWS )
		directionalLightShadow = directionalLightShadows[ i ];
		directLight.color *= ( directLight.visible && receiveShadow ) ? getShadow( directionalShadowMap[ i ], directionalLightShadow.shadowMapSize, directionalLightShadow.shadowIntensity, directionalLightShadow.shadowBias, directionalLightShadow.shadowRadius, vDirectionalShadowCoord[ i ] ) : 1.0;
		#endif
		RE_Direct( directLight, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
	}
	#pragma unroll_loop_end
#endif
#if ( NUM_RECT_AREA_LIGHTS > 0 ) && defined( RE_Direct_RectArea )
	RectAreaLight rectAreaLight;
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_RECT_AREA_LIGHTS; i ++ ) {
		rectAreaLight = rectAreaLights[ i ];
		RE_Direct_RectArea( rectAreaLight, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
	}
	#pragma unroll_loop_end
#endif
#if defined( RE_IndirectDiffuse )
	vec3 iblIrradiance = vec3( 0.0 );
	vec3 irradiance = getAmbientLightIrradiance( ambientLightColor );
	#if defined( USE_LIGHT_PROBES )
		irradiance += getLightProbeIrradiance( lightProbe, geometryNormal );
	#endif
	#if ( NUM_HEMI_LIGHTS > 0 )
		#pragma unroll_loop_start
		for ( int i = 0; i < NUM_HEMI_LIGHTS; i ++ ) {
			irradiance += getHemisphereLightIrradiance( hemisphereLights[ i ], geometryNormal );
		}
		#pragma unroll_loop_end
	#endif
#endif
#if defined( RE_IndirectSpecular )
	vec3 radiance = vec3( 0.0 );
	vec3 clearcoatRadiance = vec3( 0.0 );
#endif`,e0=`#if defined( RE_IndirectDiffuse )
	#ifdef USE_LIGHTMAP
		vec4 lightMapTexel = texture2D( lightMap, vLightMapUv );
		vec3 lightMapIrradiance = lightMapTexel.rgb * lightMapIntensity;
		irradiance += lightMapIrradiance;
	#endif
	#if defined( USE_ENVMAP ) && defined( STANDARD ) && defined( ENVMAP_TYPE_CUBE_UV )
		iblIrradiance += getIBLIrradiance( geometryNormal );
	#endif
#endif
#if defined( USE_ENVMAP ) && defined( RE_IndirectSpecular )
	#ifdef USE_ANISOTROPY
		radiance += getIBLAnisotropyRadiance( geometryViewDir, geometryNormal, material.roughness, material.anisotropyB, material.anisotropy );
	#else
		radiance += getIBLRadiance( geometryViewDir, geometryNormal, material.roughness );
	#endif
	#ifdef USE_CLEARCOAT
		clearcoatRadiance += getIBLRadiance( geometryViewDir, geometryClearcoatNormal, material.clearcoatRoughness );
	#endif
#endif`,t0=`#if defined( RE_IndirectDiffuse )
	RE_IndirectDiffuse( irradiance, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
#endif
#if defined( RE_IndirectSpecular )
	RE_IndirectSpecular( radiance, iblIrradiance, clearcoatRadiance, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
#endif`,n0=`#if defined( USE_LOGDEPTHBUF )
	gl_FragDepth = vIsPerspective == 0.0 ? gl_FragCoord.z : log2( vFragDepth ) * logDepthBufFC * 0.5;
#endif`,i0=`#if defined( USE_LOGDEPTHBUF )
	uniform float logDepthBufFC;
	varying float vFragDepth;
	varying float vIsPerspective;
#endif`,s0=`#ifdef USE_LOGDEPTHBUF
	varying float vFragDepth;
	varying float vIsPerspective;
#endif`,r0=`#ifdef USE_LOGDEPTHBUF
	vFragDepth = 1.0 + gl_Position.w;
	vIsPerspective = float( isPerspectiveMatrix( projectionMatrix ) );
#endif`,o0=`#ifdef USE_MAP
	vec4 sampledDiffuseColor = texture2D( map, vMapUv );
	#ifdef DECODE_VIDEO_TEXTURE
		sampledDiffuseColor = vec4( mix( pow( sampledDiffuseColor.rgb * 0.9478672986 + vec3( 0.0521327014 ), vec3( 2.4 ) ), sampledDiffuseColor.rgb * 0.0773993808, vec3( lessThanEqual( sampledDiffuseColor.rgb, vec3( 0.04045 ) ) ) ), sampledDiffuseColor.w );
	
	#endif
	diffuseColor *= sampledDiffuseColor;
#endif`,a0=`#ifdef USE_MAP
	uniform sampler2D map;
#endif`,l0=`#if defined( USE_MAP ) || defined( USE_ALPHAMAP )
	#if defined( USE_POINTS_UV )
		vec2 uv = vUv;
	#else
		vec2 uv = ( uvTransform * vec3( gl_PointCoord.x, 1.0 - gl_PointCoord.y, 1 ) ).xy;
	#endif
#endif
#ifdef USE_MAP
	diffuseColor *= texture2D( map, uv );
#endif
#ifdef USE_ALPHAMAP
	diffuseColor.a *= texture2D( alphaMap, uv ).g;
#endif`,c0=`#if defined( USE_POINTS_UV )
	varying vec2 vUv;
#else
	#if defined( USE_MAP ) || defined( USE_ALPHAMAP )
		uniform mat3 uvTransform;
	#endif
#endif
#ifdef USE_MAP
	uniform sampler2D map;
#endif
#ifdef USE_ALPHAMAP
	uniform sampler2D alphaMap;
#endif`,h0=`float metalnessFactor = metalness;
#ifdef USE_METALNESSMAP
	vec4 texelMetalness = texture2D( metalnessMap, vMetalnessMapUv );
	metalnessFactor *= texelMetalness.b;
#endif`,u0=`#ifdef USE_METALNESSMAP
	uniform sampler2D metalnessMap;
#endif`,d0=`#ifdef USE_INSTANCING_MORPH
	float morphTargetInfluences[ MORPHTARGETS_COUNT ];
	float morphTargetBaseInfluence = texelFetch( morphTexture, ivec2( 0, gl_InstanceID ), 0 ).r;
	for ( int i = 0; i < MORPHTARGETS_COUNT; i ++ ) {
		morphTargetInfluences[i] =  texelFetch( morphTexture, ivec2( i + 1, gl_InstanceID ), 0 ).r;
	}
#endif`,f0=`#if defined( USE_MORPHCOLORS )
	vColor *= morphTargetBaseInfluence;
	for ( int i = 0; i < MORPHTARGETS_COUNT; i ++ ) {
		#if defined( USE_COLOR_ALPHA )
			if ( morphTargetInfluences[ i ] != 0.0 ) vColor += getMorph( gl_VertexID, i, 2 ) * morphTargetInfluences[ i ];
		#elif defined( USE_COLOR )
			if ( morphTargetInfluences[ i ] != 0.0 ) vColor += getMorph( gl_VertexID, i, 2 ).rgb * morphTargetInfluences[ i ];
		#endif
	}
#endif`,p0=`#ifdef USE_MORPHNORMALS
	objectNormal *= morphTargetBaseInfluence;
	for ( int i = 0; i < MORPHTARGETS_COUNT; i ++ ) {
		if ( morphTargetInfluences[ i ] != 0.0 ) objectNormal += getMorph( gl_VertexID, i, 1 ).xyz * morphTargetInfluences[ i ];
	}
#endif`,m0=`#ifdef USE_MORPHTARGETS
	#ifndef USE_INSTANCING_MORPH
		uniform float morphTargetBaseInfluence;
		uniform float morphTargetInfluences[ MORPHTARGETS_COUNT ];
	#endif
	uniform sampler2DArray morphTargetsTexture;
	uniform ivec2 morphTargetsTextureSize;
	vec4 getMorph( const in int vertexIndex, const in int morphTargetIndex, const in int offset ) {
		int texelIndex = vertexIndex * MORPHTARGETS_TEXTURE_STRIDE + offset;
		int y = texelIndex / morphTargetsTextureSize.x;
		int x = texelIndex - y * morphTargetsTextureSize.x;
		ivec3 morphUV = ivec3( x, y, morphTargetIndex );
		return texelFetch( morphTargetsTexture, morphUV, 0 );
	}
#endif`,g0=`#ifdef USE_MORPHTARGETS
	transformed *= morphTargetBaseInfluence;
	for ( int i = 0; i < MORPHTARGETS_COUNT; i ++ ) {
		if ( morphTargetInfluences[ i ] != 0.0 ) transformed += getMorph( gl_VertexID, i, 0 ).xyz * morphTargetInfluences[ i ];
	}
#endif`,v0=`float faceDirection = gl_FrontFacing ? 1.0 : - 1.0;
#ifdef FLAT_SHADED
	vec3 fdx = dFdx( vViewPosition );
	vec3 fdy = dFdy( vViewPosition );
	vec3 normal = normalize( cross( fdx, fdy ) );
#else
	vec3 normal = normalize( vNormal );
	#ifdef DOUBLE_SIDED
		normal *= faceDirection;
	#endif
#endif
#if defined( USE_NORMALMAP_TANGENTSPACE ) || defined( USE_CLEARCOAT_NORMALMAP ) || defined( USE_ANISOTROPY )
	#ifdef USE_TANGENT
		mat3 tbn = mat3( normalize( vTangent ), normalize( vBitangent ), normal );
	#else
		mat3 tbn = getTangentFrame( - vViewPosition, normal,
		#if defined( USE_NORMALMAP )
			vNormalMapUv
		#elif defined( USE_CLEARCOAT_NORMALMAP )
			vClearcoatNormalMapUv
		#else
			vUv
		#endif
		);
	#endif
	#if defined( DOUBLE_SIDED ) && ! defined( FLAT_SHADED )
		tbn[0] *= faceDirection;
		tbn[1] *= faceDirection;
	#endif
#endif
#ifdef USE_CLEARCOAT_NORMALMAP
	#ifdef USE_TANGENT
		mat3 tbn2 = mat3( normalize( vTangent ), normalize( vBitangent ), normal );
	#else
		mat3 tbn2 = getTangentFrame( - vViewPosition, normal, vClearcoatNormalMapUv );
	#endif
	#if defined( DOUBLE_SIDED ) && ! defined( FLAT_SHADED )
		tbn2[0] *= faceDirection;
		tbn2[1] *= faceDirection;
	#endif
#endif
vec3 nonPerturbedNormal = normal;`,x0=`#ifdef USE_NORMALMAP_OBJECTSPACE
	normal = texture2D( normalMap, vNormalMapUv ).xyz * 2.0 - 1.0;
	#ifdef FLIP_SIDED
		normal = - normal;
	#endif
	#ifdef DOUBLE_SIDED
		normal = normal * faceDirection;
	#endif
	normal = normalize( normalMatrix * normal );
#elif defined( USE_NORMALMAP_TANGENTSPACE )
	vec3 mapN = texture2D( normalMap, vNormalMapUv ).xyz * 2.0 - 1.0;
	mapN.xy *= normalScale;
	normal = normalize( tbn * mapN );
#elif defined( USE_BUMPMAP )
	normal = perturbNormalArb( - vViewPosition, normal, dHdxy_fwd(), faceDirection );
#endif`,_0=`#ifndef FLAT_SHADED
	varying vec3 vNormal;
	#ifdef USE_TANGENT
		varying vec3 vTangent;
		varying vec3 vBitangent;
	#endif
#endif`,y0=`#ifndef FLAT_SHADED
	varying vec3 vNormal;
	#ifdef USE_TANGENT
		varying vec3 vTangent;
		varying vec3 vBitangent;
	#endif
#endif`,M0=`#ifndef FLAT_SHADED
	vNormal = normalize( transformedNormal );
	#ifdef USE_TANGENT
		vTangent = normalize( transformedTangent );
		vBitangent = normalize( cross( vNormal, vTangent ) * tangent.w );
	#endif
#endif`,b0=`#ifdef USE_NORMALMAP
	uniform sampler2D normalMap;
	uniform vec2 normalScale;
#endif
#ifdef USE_NORMALMAP_OBJECTSPACE
	uniform mat3 normalMatrix;
#endif
#if ! defined ( USE_TANGENT ) && ( defined ( USE_NORMALMAP_TANGENTSPACE ) || defined ( USE_CLEARCOAT_NORMALMAP ) || defined( USE_ANISOTROPY ) )
	mat3 getTangentFrame( vec3 eye_pos, vec3 surf_norm, vec2 uv ) {
		vec3 q0 = dFdx( eye_pos.xyz );
		vec3 q1 = dFdy( eye_pos.xyz );
		vec2 st0 = dFdx( uv.st );
		vec2 st1 = dFdy( uv.st );
		vec3 N = surf_norm;
		vec3 q1perp = cross( q1, N );
		vec3 q0perp = cross( N, q0 );
		vec3 T = q1perp * st0.x + q0perp * st1.x;
		vec3 B = q1perp * st0.y + q0perp * st1.y;
		float det = max( dot( T, T ), dot( B, B ) );
		float scale = ( det == 0.0 ) ? 0.0 : inversesqrt( det );
		return mat3( T * scale, B * scale, N );
	}
#endif`,w0=`#ifdef USE_CLEARCOAT
	vec3 clearcoatNormal = nonPerturbedNormal;
#endif`,S0=`#ifdef USE_CLEARCOAT_NORMALMAP
	vec3 clearcoatMapN = texture2D( clearcoatNormalMap, vClearcoatNormalMapUv ).xyz * 2.0 - 1.0;
	clearcoatMapN.xy *= clearcoatNormalScale;
	clearcoatNormal = normalize( tbn2 * clearcoatMapN );
#endif`,T0=`#ifdef USE_CLEARCOATMAP
	uniform sampler2D clearcoatMap;
#endif
#ifdef USE_CLEARCOAT_NORMALMAP
	uniform sampler2D clearcoatNormalMap;
	uniform vec2 clearcoatNormalScale;
#endif
#ifdef USE_CLEARCOAT_ROUGHNESSMAP
	uniform sampler2D clearcoatRoughnessMap;
#endif`,E0=`#ifdef USE_IRIDESCENCEMAP
	uniform sampler2D iridescenceMap;
#endif
#ifdef USE_IRIDESCENCE_THICKNESSMAP
	uniform sampler2D iridescenceThicknessMap;
#endif`,A0=`#ifdef OPAQUE
diffuseColor.a = 1.0;
#endif
#ifdef USE_TRANSMISSION
diffuseColor.a *= material.transmissionAlpha;
#endif
gl_FragColor = vec4( outgoingLight, diffuseColor.a );`,C0=`vec3 packNormalToRGB( const in vec3 normal ) {
	return normalize( normal ) * 0.5 + 0.5;
}
vec3 unpackRGBToNormal( const in vec3 rgb ) {
	return 2.0 * rgb.xyz - 1.0;
}
const float PackUpscale = 256. / 255.;const float UnpackDownscale = 255. / 256.;const float ShiftRight8 = 1. / 256.;
const float Inv255 = 1. / 255.;
const vec4 PackFactors = vec4( 1.0, 256.0, 256.0 * 256.0, 256.0 * 256.0 * 256.0 );
const vec2 UnpackFactors2 = vec2( UnpackDownscale, 1.0 / PackFactors.g );
const vec3 UnpackFactors3 = vec3( UnpackDownscale / PackFactors.rg, 1.0 / PackFactors.b );
const vec4 UnpackFactors4 = vec4( UnpackDownscale / PackFactors.rgb, 1.0 / PackFactors.a );
vec4 packDepthToRGBA( const in float v ) {
	if( v <= 0.0 )
		return vec4( 0., 0., 0., 0. );
	if( v >= 1.0 )
		return vec4( 1., 1., 1., 1. );
	float vuf;
	float af = modf( v * PackFactors.a, vuf );
	float bf = modf( vuf * ShiftRight8, vuf );
	float gf = modf( vuf * ShiftRight8, vuf );
	return vec4( vuf * Inv255, gf * PackUpscale, bf * PackUpscale, af );
}
vec3 packDepthToRGB( const in float v ) {
	if( v <= 0.0 )
		return vec3( 0., 0., 0. );
	if( v >= 1.0 )
		return vec3( 1., 1., 1. );
	float vuf;
	float bf = modf( v * PackFactors.b, vuf );
	float gf = modf( vuf * ShiftRight8, vuf );
	return vec3( vuf * Inv255, gf * PackUpscale, bf );
}
vec2 packDepthToRG( const in float v ) {
	if( v <= 0.0 )
		return vec2( 0., 0. );
	if( v >= 1.0 )
		return vec2( 1., 1. );
	float vuf;
	float gf = modf( v * 256., vuf );
	return vec2( vuf * Inv255, gf );
}
float unpackRGBAToDepth( const in vec4 v ) {
	return dot( v, UnpackFactors4 );
}
float unpackRGBToDepth( const in vec3 v ) {
	return dot( v, UnpackFactors3 );
}
float unpackRGToDepth( const in vec2 v ) {
	return v.r * UnpackFactors2.r + v.g * UnpackFactors2.g;
}
vec4 pack2HalfToRGBA( const in vec2 v ) {
	vec4 r = vec4( v.x, fract( v.x * 255.0 ), v.y, fract( v.y * 255.0 ) );
	return vec4( r.x - r.y / 255.0, r.y, r.z - r.w / 255.0, r.w );
}
vec2 unpackRGBATo2Half( const in vec4 v ) {
	return vec2( v.x + ( v.y / 255.0 ), v.z + ( v.w / 255.0 ) );
}
float viewZToOrthographicDepth( const in float viewZ, const in float near, const in float far ) {
	return ( viewZ + near ) / ( near - far );
}
float orthographicDepthToViewZ( const in float depth, const in float near, const in float far ) {
	return depth * ( near - far ) - near;
}
float viewZToPerspectiveDepth( const in float viewZ, const in float near, const in float far ) {
	return ( ( near + viewZ ) * far ) / ( ( far - near ) * viewZ );
}
float perspectiveDepthToViewZ( const in float depth, const in float near, const in float far ) {
	return ( near * far ) / ( ( far - near ) * depth - far );
}`,P0=`#ifdef PREMULTIPLIED_ALPHA
	gl_FragColor.rgb *= gl_FragColor.a;
#endif`,R0=`vec4 mvPosition = vec4( transformed, 1.0 );
#ifdef USE_BATCHING
	mvPosition = batchingMatrix * mvPosition;
#endif
#ifdef USE_INSTANCING
	mvPosition = instanceMatrix * mvPosition;
#endif
mvPosition = modelViewMatrix * mvPosition;
gl_Position = projectionMatrix * mvPosition;`,D0=`#ifdef DITHERING
	gl_FragColor.rgb = dithering( gl_FragColor.rgb );
#endif`,I0=`#ifdef DITHERING
	vec3 dithering( vec3 color ) {
		float grid_position = rand( gl_FragCoord.xy );
		vec3 dither_shift_RGB = vec3( 0.25 / 255.0, -0.25 / 255.0, 0.25 / 255.0 );
		dither_shift_RGB = mix( 2.0 * dither_shift_RGB, -2.0 * dither_shift_RGB, grid_position );
		return color + dither_shift_RGB;
	}
#endif`,L0=`float roughnessFactor = roughness;
#ifdef USE_ROUGHNESSMAP
	vec4 texelRoughness = texture2D( roughnessMap, vRoughnessMapUv );
	roughnessFactor *= texelRoughness.g;
#endif`,N0=`#ifdef USE_ROUGHNESSMAP
	uniform sampler2D roughnessMap;
#endif`,U0=`#if NUM_SPOT_LIGHT_COORDS > 0
	varying vec4 vSpotLightCoord[ NUM_SPOT_LIGHT_COORDS ];
#endif
#if NUM_SPOT_LIGHT_MAPS > 0
	uniform sampler2D spotLightMap[ NUM_SPOT_LIGHT_MAPS ];
#endif
#ifdef USE_SHADOWMAP
	#if NUM_DIR_LIGHT_SHADOWS > 0
		uniform sampler2D directionalShadowMap[ NUM_DIR_LIGHT_SHADOWS ];
		varying vec4 vDirectionalShadowCoord[ NUM_DIR_LIGHT_SHADOWS ];
		struct DirectionalLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
		};
		uniform DirectionalLightShadow directionalLightShadows[ NUM_DIR_LIGHT_SHADOWS ];
	#endif
	#if NUM_SPOT_LIGHT_SHADOWS > 0
		uniform sampler2D spotShadowMap[ NUM_SPOT_LIGHT_SHADOWS ];
		struct SpotLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
		};
		uniform SpotLightShadow spotLightShadows[ NUM_SPOT_LIGHT_SHADOWS ];
	#endif
	#if NUM_POINT_LIGHT_SHADOWS > 0
		uniform sampler2D pointShadowMap[ NUM_POINT_LIGHT_SHADOWS ];
		varying vec4 vPointShadowCoord[ NUM_POINT_LIGHT_SHADOWS ];
		struct PointLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
			float shadowCameraNear;
			float shadowCameraFar;
		};
		uniform PointLightShadow pointLightShadows[ NUM_POINT_LIGHT_SHADOWS ];
	#endif
	float texture2DCompare( sampler2D depths, vec2 uv, float compare ) {
		return step( compare, unpackRGBAToDepth( texture2D( depths, uv ) ) );
	}
	vec2 texture2DDistribution( sampler2D shadow, vec2 uv ) {
		return unpackRGBATo2Half( texture2D( shadow, uv ) );
	}
	float VSMShadow (sampler2D shadow, vec2 uv, float compare ){
		float occlusion = 1.0;
		vec2 distribution = texture2DDistribution( shadow, uv );
		float hard_shadow = step( compare , distribution.x );
		if (hard_shadow != 1.0 ) {
			float distance = compare - distribution.x ;
			float variance = max( 0.00000, distribution.y * distribution.y );
			float softness_probability = variance / (variance + distance * distance );			softness_probability = clamp( ( softness_probability - 0.3 ) / ( 0.95 - 0.3 ), 0.0, 1.0 );			occlusion = clamp( max( hard_shadow, softness_probability ), 0.0, 1.0 );
		}
		return occlusion;
	}
	float getShadow( sampler2D shadowMap, vec2 shadowMapSize, float shadowIntensity, float shadowBias, float shadowRadius, vec4 shadowCoord ) {
		float shadow = 1.0;
		shadowCoord.xyz /= shadowCoord.w;
		shadowCoord.z += shadowBias;
		bool inFrustum = shadowCoord.x >= 0.0 && shadowCoord.x <= 1.0 && shadowCoord.y >= 0.0 && shadowCoord.y <= 1.0;
		bool frustumTest = inFrustum && shadowCoord.z <= 1.0;
		if ( frustumTest ) {
		#if defined( SHADOWMAP_TYPE_PCF )
			vec2 texelSize = vec2( 1.0 ) / shadowMapSize;
			float dx0 = - texelSize.x * shadowRadius;
			float dy0 = - texelSize.y * shadowRadius;
			float dx1 = + texelSize.x * shadowRadius;
			float dy1 = + texelSize.y * shadowRadius;
			float dx2 = dx0 / 2.0;
			float dy2 = dy0 / 2.0;
			float dx3 = dx1 / 2.0;
			float dy3 = dy1 / 2.0;
			shadow = (
				texture2DCompare( shadowMap, shadowCoord.xy + vec2( dx0, dy0 ), shadowCoord.z ) +
				texture2DCompare( shadowMap, shadowCoord.xy + vec2( 0.0, dy0 ), shadowCoord.z ) +
				texture2DCompare( shadowMap, shadowCoord.xy + vec2( dx1, dy0 ), shadowCoord.z ) +
				texture2DCompare( shadowMap, shadowCoord.xy + vec2( dx2, dy2 ), shadowCoord.z ) +
				texture2DCompare( shadowMap, shadowCoord.xy + vec2( 0.0, dy2 ), shadowCoord.z ) +
				texture2DCompare( shadowMap, shadowCoord.xy + vec2( dx3, dy2 ), shadowCoord.z ) +
				texture2DCompare( shadowMap, shadowCoord.xy + vec2( dx0, 0.0 ), shadowCoord.z ) +
				texture2DCompare( shadowMap, shadowCoord.xy + vec2( dx2, 0.0 ), shadowCoord.z ) +
				texture2DCompare( shadowMap, shadowCoord.xy, shadowCoord.z ) +
				texture2DCompare( shadowMap, shadowCoord.xy + vec2( dx3, 0.0 ), shadowCoord.z ) +
				texture2DCompare( shadowMap, shadowCoord.xy + vec2( dx1, 0.0 ), shadowCoord.z ) +
				texture2DCompare( shadowMap, shadowCoord.xy + vec2( dx2, dy3 ), shadowCoord.z ) +
				texture2DCompare( shadowMap, shadowCoord.xy + vec2( 0.0, dy3 ), shadowCoord.z ) +
				texture2DCompare( shadowMap, shadowCoord.xy + vec2( dx3, dy3 ), shadowCoord.z ) +
				texture2DCompare( shadowMap, shadowCoord.xy + vec2( dx0, dy1 ), shadowCoord.z ) +
				texture2DCompare( shadowMap, shadowCoord.xy + vec2( 0.0, dy1 ), shadowCoord.z ) +
				texture2DCompare( shadowMap, shadowCoord.xy + vec2( dx1, dy1 ), shadowCoord.z )
			) * ( 1.0 / 17.0 );
		#elif defined( SHADOWMAP_TYPE_PCF_SOFT )
			vec2 texelSize = vec2( 1.0 ) / shadowMapSize;
			float dx = texelSize.x;
			float dy = texelSize.y;
			vec2 uv = shadowCoord.xy;
			vec2 f = fract( uv * shadowMapSize + 0.5 );
			uv -= f * texelSize;
			shadow = (
				texture2DCompare( shadowMap, uv, shadowCoord.z ) +
				texture2DCompare( shadowMap, uv + vec2( dx, 0.0 ), shadowCoord.z ) +
				texture2DCompare( shadowMap, uv + vec2( 0.0, dy ), shadowCoord.z ) +
				texture2DCompare( shadowMap, uv + texelSize, shadowCoord.z ) +
				mix( texture2DCompare( shadowMap, uv + vec2( -dx, 0.0 ), shadowCoord.z ),
					 texture2DCompare( shadowMap, uv + vec2( 2.0 * dx, 0.0 ), shadowCoord.z ),
					 f.x ) +
				mix( texture2DCompare( shadowMap, uv + vec2( -dx, dy ), shadowCoord.z ),
					 texture2DCompare( shadowMap, uv + vec2( 2.0 * dx, dy ), shadowCoord.z ),
					 f.x ) +
				mix( texture2DCompare( shadowMap, uv + vec2( 0.0, -dy ), shadowCoord.z ),
					 texture2DCompare( shadowMap, uv + vec2( 0.0, 2.0 * dy ), shadowCoord.z ),
					 f.y ) +
				mix( texture2DCompare( shadowMap, uv + vec2( dx, -dy ), shadowCoord.z ),
					 texture2DCompare( shadowMap, uv + vec2( dx, 2.0 * dy ), shadowCoord.z ),
					 f.y ) +
				mix( mix( texture2DCompare( shadowMap, uv + vec2( -dx, -dy ), shadowCoord.z ),
						  texture2DCompare( shadowMap, uv + vec2( 2.0 * dx, -dy ), shadowCoord.z ),
						  f.x ),
					 mix( texture2DCompare( shadowMap, uv + vec2( -dx, 2.0 * dy ), shadowCoord.z ),
						  texture2DCompare( shadowMap, uv + vec2( 2.0 * dx, 2.0 * dy ), shadowCoord.z ),
						  f.x ),
					 f.y )
			) * ( 1.0 / 9.0 );
		#elif defined( SHADOWMAP_TYPE_VSM )
			shadow = VSMShadow( shadowMap, shadowCoord.xy, shadowCoord.z );
		#else
			shadow = texture2DCompare( shadowMap, shadowCoord.xy, shadowCoord.z );
		#endif
		}
		return mix( 1.0, shadow, shadowIntensity );
	}
	vec2 cubeToUV( vec3 v, float texelSizeY ) {
		vec3 absV = abs( v );
		float scaleToCube = 1.0 / max( absV.x, max( absV.y, absV.z ) );
		absV *= scaleToCube;
		v *= scaleToCube * ( 1.0 - 2.0 * texelSizeY );
		vec2 planar = v.xy;
		float almostATexel = 1.5 * texelSizeY;
		float almostOne = 1.0 - almostATexel;
		if ( absV.z >= almostOne ) {
			if ( v.z > 0.0 )
				planar.x = 4.0 - v.x;
		} else if ( absV.x >= almostOne ) {
			float signX = sign( v.x );
			planar.x = v.z * signX + 2.0 * signX;
		} else if ( absV.y >= almostOne ) {
			float signY = sign( v.y );
			planar.x = v.x + 2.0 * signY + 2.0;
			planar.y = v.z * signY - 2.0;
		}
		return vec2( 0.125, 0.25 ) * planar + vec2( 0.375, 0.75 );
	}
	float getPointShadow( sampler2D shadowMap, vec2 shadowMapSize, float shadowIntensity, float shadowBias, float shadowRadius, vec4 shadowCoord, float shadowCameraNear, float shadowCameraFar ) {
		float shadow = 1.0;
		vec3 lightToPosition = shadowCoord.xyz;
		
		float lightToPositionLength = length( lightToPosition );
		if ( lightToPositionLength - shadowCameraFar <= 0.0 && lightToPositionLength - shadowCameraNear >= 0.0 ) {
			float dp = ( lightToPositionLength - shadowCameraNear ) / ( shadowCameraFar - shadowCameraNear );			dp += shadowBias;
			vec3 bd3D = normalize( lightToPosition );
			vec2 texelSize = vec2( 1.0 ) / ( shadowMapSize * vec2( 4.0, 2.0 ) );
			#if defined( SHADOWMAP_TYPE_PCF ) || defined( SHADOWMAP_TYPE_PCF_SOFT ) || defined( SHADOWMAP_TYPE_VSM )
				vec2 offset = vec2( - 1, 1 ) * shadowRadius * texelSize.y;
				shadow = (
					texture2DCompare( shadowMap, cubeToUV( bd3D + offset.xyy, texelSize.y ), dp ) +
					texture2DCompare( shadowMap, cubeToUV( bd3D + offset.yyy, texelSize.y ), dp ) +
					texture2DCompare( shadowMap, cubeToUV( bd3D + offset.xyx, texelSize.y ), dp ) +
					texture2DCompare( shadowMap, cubeToUV( bd3D + offset.yyx, texelSize.y ), dp ) +
					texture2DCompare( shadowMap, cubeToUV( bd3D, texelSize.y ), dp ) +
					texture2DCompare( shadowMap, cubeToUV( bd3D + offset.xxy, texelSize.y ), dp ) +
					texture2DCompare( shadowMap, cubeToUV( bd3D + offset.yxy, texelSize.y ), dp ) +
					texture2DCompare( shadowMap, cubeToUV( bd3D + offset.xxx, texelSize.y ), dp ) +
					texture2DCompare( shadowMap, cubeToUV( bd3D + offset.yxx, texelSize.y ), dp )
				) * ( 1.0 / 9.0 );
			#else
				shadow = texture2DCompare( shadowMap, cubeToUV( bd3D, texelSize.y ), dp );
			#endif
		}
		return mix( 1.0, shadow, shadowIntensity );
	}
#endif`,O0=`#if NUM_SPOT_LIGHT_COORDS > 0
	uniform mat4 spotLightMatrix[ NUM_SPOT_LIGHT_COORDS ];
	varying vec4 vSpotLightCoord[ NUM_SPOT_LIGHT_COORDS ];
#endif
#ifdef USE_SHADOWMAP
	#if NUM_DIR_LIGHT_SHADOWS > 0
		uniform mat4 directionalShadowMatrix[ NUM_DIR_LIGHT_SHADOWS ];
		varying vec4 vDirectionalShadowCoord[ NUM_DIR_LIGHT_SHADOWS ];
		struct DirectionalLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
		};
		uniform DirectionalLightShadow directionalLightShadows[ NUM_DIR_LIGHT_SHADOWS ];
	#endif
	#if NUM_SPOT_LIGHT_SHADOWS > 0
		struct SpotLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
		};
		uniform SpotLightShadow spotLightShadows[ NUM_SPOT_LIGHT_SHADOWS ];
	#endif
	#if NUM_POINT_LIGHT_SHADOWS > 0
		uniform mat4 pointShadowMatrix[ NUM_POINT_LIGHT_SHADOWS ];
		varying vec4 vPointShadowCoord[ NUM_POINT_LIGHT_SHADOWS ];
		struct PointLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
			float shadowCameraNear;
			float shadowCameraFar;
		};
		uniform PointLightShadow pointLightShadows[ NUM_POINT_LIGHT_SHADOWS ];
	#endif
#endif`,F0=`#if ( defined( USE_SHADOWMAP ) && ( NUM_DIR_LIGHT_SHADOWS > 0 || NUM_POINT_LIGHT_SHADOWS > 0 ) ) || ( NUM_SPOT_LIGHT_COORDS > 0 )
	vec3 shadowWorldNormal = inverseTransformDirection( transformedNormal, viewMatrix );
	vec4 shadowWorldPosition;
#endif
#if defined( USE_SHADOWMAP )
	#if NUM_DIR_LIGHT_SHADOWS > 0
		#pragma unroll_loop_start
		for ( int i = 0; i < NUM_DIR_LIGHT_SHADOWS; i ++ ) {
			shadowWorldPosition = worldPosition + vec4( shadowWorldNormal * directionalLightShadows[ i ].shadowNormalBias, 0 );
			vDirectionalShadowCoord[ i ] = directionalShadowMatrix[ i ] * shadowWorldPosition;
		}
		#pragma unroll_loop_end
	#endif
	#if NUM_POINT_LIGHT_SHADOWS > 0
		#pragma unroll_loop_start
		for ( int i = 0; i < NUM_POINT_LIGHT_SHADOWS; i ++ ) {
			shadowWorldPosition = worldPosition + vec4( shadowWorldNormal * pointLightShadows[ i ].shadowNormalBias, 0 );
			vPointShadowCoord[ i ] = pointShadowMatrix[ i ] * shadowWorldPosition;
		}
		#pragma unroll_loop_end
	#endif
#endif
#if NUM_SPOT_LIGHT_COORDS > 0
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_SPOT_LIGHT_COORDS; i ++ ) {
		shadowWorldPosition = worldPosition;
		#if ( defined( USE_SHADOWMAP ) && UNROLLED_LOOP_INDEX < NUM_SPOT_LIGHT_SHADOWS )
			shadowWorldPosition.xyz += shadowWorldNormal * spotLightShadows[ i ].shadowNormalBias;
		#endif
		vSpotLightCoord[ i ] = spotLightMatrix[ i ] * shadowWorldPosition;
	}
	#pragma unroll_loop_end
#endif`,z0=`float getShadowMask() {
	float shadow = 1.0;
	#ifdef USE_SHADOWMAP
	#if NUM_DIR_LIGHT_SHADOWS > 0
	DirectionalLightShadow directionalLight;
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_DIR_LIGHT_SHADOWS; i ++ ) {
		directionalLight = directionalLightShadows[ i ];
		shadow *= receiveShadow ? getShadow( directionalShadowMap[ i ], directionalLight.shadowMapSize, directionalLight.shadowIntensity, directionalLight.shadowBias, directionalLight.shadowRadius, vDirectionalShadowCoord[ i ] ) : 1.0;
	}
	#pragma unroll_loop_end
	#endif
	#if NUM_SPOT_LIGHT_SHADOWS > 0
	SpotLightShadow spotLight;
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_SPOT_LIGHT_SHADOWS; i ++ ) {
		spotLight = spotLightShadows[ i ];
		shadow *= receiveShadow ? getShadow( spotShadowMap[ i ], spotLight.shadowMapSize, spotLight.shadowIntensity, spotLight.shadowBias, spotLight.shadowRadius, vSpotLightCoord[ i ] ) : 1.0;
	}
	#pragma unroll_loop_end
	#endif
	#if NUM_POINT_LIGHT_SHADOWS > 0
	PointLightShadow pointLight;
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_POINT_LIGHT_SHADOWS; i ++ ) {
		pointLight = pointLightShadows[ i ];
		shadow *= receiveShadow ? getPointShadow( pointShadowMap[ i ], pointLight.shadowMapSize, pointLight.shadowIntensity, pointLight.shadowBias, pointLight.shadowRadius, vPointShadowCoord[ i ], pointLight.shadowCameraNear, pointLight.shadowCameraFar ) : 1.0;
	}
	#pragma unroll_loop_end
	#endif
	#endif
	return shadow;
}`,k0=`#ifdef USE_SKINNING
	mat4 boneMatX = getBoneMatrix( skinIndex.x );
	mat4 boneMatY = getBoneMatrix( skinIndex.y );
	mat4 boneMatZ = getBoneMatrix( skinIndex.z );
	mat4 boneMatW = getBoneMatrix( skinIndex.w );
#endif`,B0=`#ifdef USE_SKINNING
	uniform mat4 bindMatrix;
	uniform mat4 bindMatrixInverse;
	uniform highp sampler2D boneTexture;
	mat4 getBoneMatrix( const in float i ) {
		int size = textureSize( boneTexture, 0 ).x;
		int j = int( i ) * 4;
		int x = j % size;
		int y = j / size;
		vec4 v1 = texelFetch( boneTexture, ivec2( x, y ), 0 );
		vec4 v2 = texelFetch( boneTexture, ivec2( x + 1, y ), 0 );
		vec4 v3 = texelFetch( boneTexture, ivec2( x + 2, y ), 0 );
		vec4 v4 = texelFetch( boneTexture, ivec2( x + 3, y ), 0 );
		return mat4( v1, v2, v3, v4 );
	}
#endif`,V0=`#ifdef USE_SKINNING
	vec4 skinVertex = bindMatrix * vec4( transformed, 1.0 );
	vec4 skinned = vec4( 0.0 );
	skinned += boneMatX * skinVertex * skinWeight.x;
	skinned += boneMatY * skinVertex * skinWeight.y;
	skinned += boneMatZ * skinVertex * skinWeight.z;
	skinned += boneMatW * skinVertex * skinWeight.w;
	transformed = ( bindMatrixInverse * skinned ).xyz;
#endif`,H0=`#ifdef USE_SKINNING
	mat4 skinMatrix = mat4( 0.0 );
	skinMatrix += skinWeight.x * boneMatX;
	skinMatrix += skinWeight.y * boneMatY;
	skinMatrix += skinWeight.z * boneMatZ;
	skinMatrix += skinWeight.w * boneMatW;
	skinMatrix = bindMatrixInverse * skinMatrix * bindMatrix;
	objectNormal = vec4( skinMatrix * vec4( objectNormal, 0.0 ) ).xyz;
	#ifdef USE_TANGENT
		objectTangent = vec4( skinMatrix * vec4( objectTangent, 0.0 ) ).xyz;
	#endif
#endif`,G0=`float specularStrength;
#ifdef USE_SPECULARMAP
	vec4 texelSpecular = texture2D( specularMap, vSpecularMapUv );
	specularStrength = texelSpecular.r;
#else
	specularStrength = 1.0;
#endif`,W0=`#ifdef USE_SPECULARMAP
	uniform sampler2D specularMap;
#endif`,X0=`#if defined( TONE_MAPPING )
	gl_FragColor.rgb = toneMapping( gl_FragColor.rgb );
#endif`,Y0=`#ifndef saturate
#define saturate( a ) clamp( a, 0.0, 1.0 )
#endif
uniform float toneMappingExposure;
vec3 LinearToneMapping( vec3 color ) {
	return saturate( toneMappingExposure * color );
}
vec3 ReinhardToneMapping( vec3 color ) {
	color *= toneMappingExposure;
	return saturate( color / ( vec3( 1.0 ) + color ) );
}
vec3 CineonToneMapping( vec3 color ) {
	color *= toneMappingExposure;
	color = max( vec3( 0.0 ), color - 0.004 );
	return pow( ( color * ( 6.2 * color + 0.5 ) ) / ( color * ( 6.2 * color + 1.7 ) + 0.06 ), vec3( 2.2 ) );
}
vec3 RRTAndODTFit( vec3 v ) {
	vec3 a = v * ( v + 0.0245786 ) - 0.000090537;
	vec3 b = v * ( 0.983729 * v + 0.4329510 ) + 0.238081;
	return a / b;
}
vec3 ACESFilmicToneMapping( vec3 color ) {
	const mat3 ACESInputMat = mat3(
		vec3( 0.59719, 0.07600, 0.02840 ),		vec3( 0.35458, 0.90834, 0.13383 ),
		vec3( 0.04823, 0.01566, 0.83777 )
	);
	const mat3 ACESOutputMat = mat3(
		vec3(  1.60475, -0.10208, -0.00327 ),		vec3( -0.53108,  1.10813, -0.07276 ),
		vec3( -0.07367, -0.00605,  1.07602 )
	);
	color *= toneMappingExposure / 0.6;
	color = ACESInputMat * color;
	color = RRTAndODTFit( color );
	color = ACESOutputMat * color;
	return saturate( color );
}
const mat3 LINEAR_REC2020_TO_LINEAR_SRGB = mat3(
	vec3( 1.6605, - 0.1246, - 0.0182 ),
	vec3( - 0.5876, 1.1329, - 0.1006 ),
	vec3( - 0.0728, - 0.0083, 1.1187 )
);
const mat3 LINEAR_SRGB_TO_LINEAR_REC2020 = mat3(
	vec3( 0.6274, 0.0691, 0.0164 ),
	vec3( 0.3293, 0.9195, 0.0880 ),
	vec3( 0.0433, 0.0113, 0.8956 )
);
vec3 agxDefaultContrastApprox( vec3 x ) {
	vec3 x2 = x * x;
	vec3 x4 = x2 * x2;
	return + 15.5 * x4 * x2
		- 40.14 * x4 * x
		+ 31.96 * x4
		- 6.868 * x2 * x
		+ 0.4298 * x2
		+ 0.1191 * x
		- 0.00232;
}
vec3 AgXToneMapping( vec3 color ) {
	const mat3 AgXInsetMatrix = mat3(
		vec3( 0.856627153315983, 0.137318972929847, 0.11189821299995 ),
		vec3( 0.0951212405381588, 0.761241990602591, 0.0767994186031903 ),
		vec3( 0.0482516061458583, 0.101439036467562, 0.811302368396859 )
	);
	const mat3 AgXOutsetMatrix = mat3(
		vec3( 1.1271005818144368, - 0.1413297634984383, - 0.14132976349843826 ),
		vec3( - 0.11060664309660323, 1.157823702216272, - 0.11060664309660294 ),
		vec3( - 0.016493938717834573, - 0.016493938717834257, 1.2519364065950405 )
	);
	const float AgxMinEv = - 12.47393;	const float AgxMaxEv = 4.026069;
	color *= toneMappingExposure;
	color = LINEAR_SRGB_TO_LINEAR_REC2020 * color;
	color = AgXInsetMatrix * color;
	color = max( color, 1e-10 );	color = log2( color );
	color = ( color - AgxMinEv ) / ( AgxMaxEv - AgxMinEv );
	color = clamp( color, 0.0, 1.0 );
	color = agxDefaultContrastApprox( color );
	color = AgXOutsetMatrix * color;
	color = pow( max( vec3( 0.0 ), color ), vec3( 2.2 ) );
	color = LINEAR_REC2020_TO_LINEAR_SRGB * color;
	color = clamp( color, 0.0, 1.0 );
	return color;
}
vec3 NeutralToneMapping( vec3 color ) {
	const float StartCompression = 0.8 - 0.04;
	const float Desaturation = 0.15;
	color *= toneMappingExposure;
	float x = min( color.r, min( color.g, color.b ) );
	float offset = x < 0.08 ? x - 6.25 * x * x : 0.04;
	color -= offset;
	float peak = max( color.r, max( color.g, color.b ) );
	if ( peak < StartCompression ) return color;
	float d = 1. - StartCompression;
	float newPeak = 1. - d * d / ( peak + d - StartCompression );
	color *= newPeak / peak;
	float g = 1. - 1. / ( Desaturation * ( peak - newPeak ) + 1. );
	return mix( color, vec3( newPeak ), g );
}
vec3 CustomToneMapping( vec3 color ) { return color; }`,q0=`#ifdef USE_TRANSMISSION
	material.transmission = transmission;
	material.transmissionAlpha = 1.0;
	material.thickness = thickness;
	material.attenuationDistance = attenuationDistance;
	material.attenuationColor = attenuationColor;
	#ifdef USE_TRANSMISSIONMAP
		material.transmission *= texture2D( transmissionMap, vTransmissionMapUv ).r;
	#endif
	#ifdef USE_THICKNESSMAP
		material.thickness *= texture2D( thicknessMap, vThicknessMapUv ).g;
	#endif
	vec3 pos = vWorldPosition;
	vec3 v = normalize( cameraPosition - pos );
	vec3 n = inverseTransformDirection( normal, viewMatrix );
	vec4 transmitted = getIBLVolumeRefraction(
		n, v, material.roughness, material.diffuseColor, material.specularColor, material.specularF90,
		pos, modelMatrix, viewMatrix, projectionMatrix, material.dispersion, material.ior, material.thickness,
		material.attenuationColor, material.attenuationDistance );
	material.transmissionAlpha = mix( material.transmissionAlpha, transmitted.a, material.transmission );
	totalDiffuse = mix( totalDiffuse, transmitted.rgb, material.transmission );
#endif`,j0=`#ifdef USE_TRANSMISSION
	uniform float transmission;
	uniform float thickness;
	uniform float attenuationDistance;
	uniform vec3 attenuationColor;
	#ifdef USE_TRANSMISSIONMAP
		uniform sampler2D transmissionMap;
	#endif
	#ifdef USE_THICKNESSMAP
		uniform sampler2D thicknessMap;
	#endif
	uniform vec2 transmissionSamplerSize;
	uniform sampler2D transmissionSamplerMap;
	uniform mat4 modelMatrix;
	uniform mat4 projectionMatrix;
	varying vec3 vWorldPosition;
	float w0( float a ) {
		return ( 1.0 / 6.0 ) * ( a * ( a * ( - a + 3.0 ) - 3.0 ) + 1.0 );
	}
	float w1( float a ) {
		return ( 1.0 / 6.0 ) * ( a *  a * ( 3.0 * a - 6.0 ) + 4.0 );
	}
	float w2( float a ){
		return ( 1.0 / 6.0 ) * ( a * ( a * ( - 3.0 * a + 3.0 ) + 3.0 ) + 1.0 );
	}
	float w3( float a ) {
		return ( 1.0 / 6.0 ) * ( a * a * a );
	}
	float g0( float a ) {
		return w0( a ) + w1( a );
	}
	float g1( float a ) {
		return w2( a ) + w3( a );
	}
	float h0( float a ) {
		return - 1.0 + w1( a ) / ( w0( a ) + w1( a ) );
	}
	float h1( float a ) {
		return 1.0 + w3( a ) / ( w2( a ) + w3( a ) );
	}
	vec4 bicubic( sampler2D tex, vec2 uv, vec4 texelSize, float lod ) {
		uv = uv * texelSize.zw + 0.5;
		vec2 iuv = floor( uv );
		vec2 fuv = fract( uv );
		float g0x = g0( fuv.x );
		float g1x = g1( fuv.x );
		float h0x = h0( fuv.x );
		float h1x = h1( fuv.x );
		float h0y = h0( fuv.y );
		float h1y = h1( fuv.y );
		vec2 p0 = ( vec2( iuv.x + h0x, iuv.y + h0y ) - 0.5 ) * texelSize.xy;
		vec2 p1 = ( vec2( iuv.x + h1x, iuv.y + h0y ) - 0.5 ) * texelSize.xy;
		vec2 p2 = ( vec2( iuv.x + h0x, iuv.y + h1y ) - 0.5 ) * texelSize.xy;
		vec2 p3 = ( vec2( iuv.x + h1x, iuv.y + h1y ) - 0.5 ) * texelSize.xy;
		return g0( fuv.y ) * ( g0x * textureLod( tex, p0, lod ) + g1x * textureLod( tex, p1, lod ) ) +
			g1( fuv.y ) * ( g0x * textureLod( tex, p2, lod ) + g1x * textureLod( tex, p3, lod ) );
	}
	vec4 textureBicubic( sampler2D sampler, vec2 uv, float lod ) {
		vec2 fLodSize = vec2( textureSize( sampler, int( lod ) ) );
		vec2 cLodSize = vec2( textureSize( sampler, int( lod + 1.0 ) ) );
		vec2 fLodSizeInv = 1.0 / fLodSize;
		vec2 cLodSizeInv = 1.0 / cLodSize;
		vec4 fSample = bicubic( sampler, uv, vec4( fLodSizeInv, fLodSize ), floor( lod ) );
		vec4 cSample = bicubic( sampler, uv, vec4( cLodSizeInv, cLodSize ), ceil( lod ) );
		return mix( fSample, cSample, fract( lod ) );
	}
	vec3 getVolumeTransmissionRay( const in vec3 n, const in vec3 v, const in float thickness, const in float ior, const in mat4 modelMatrix ) {
		vec3 refractionVector = refract( - v, normalize( n ), 1.0 / ior );
		vec3 modelScale;
		modelScale.x = length( vec3( modelMatrix[ 0 ].xyz ) );
		modelScale.y = length( vec3( modelMatrix[ 1 ].xyz ) );
		modelScale.z = length( vec3( modelMatrix[ 2 ].xyz ) );
		return normalize( refractionVector ) * thickness * modelScale;
	}
	float applyIorToRoughness( const in float roughness, const in float ior ) {
		return roughness * clamp( ior * 2.0 - 2.0, 0.0, 1.0 );
	}
	vec4 getTransmissionSample( const in vec2 fragCoord, const in float roughness, const in float ior ) {
		float lod = log2( transmissionSamplerSize.x ) * applyIorToRoughness( roughness, ior );
		return textureBicubic( transmissionSamplerMap, fragCoord.xy, lod );
	}
	vec3 volumeAttenuation( const in float transmissionDistance, const in vec3 attenuationColor, const in float attenuationDistance ) {
		if ( isinf( attenuationDistance ) ) {
			return vec3( 1.0 );
		} else {
			vec3 attenuationCoefficient = -log( attenuationColor ) / attenuationDistance;
			vec3 transmittance = exp( - attenuationCoefficient * transmissionDistance );			return transmittance;
		}
	}
	vec4 getIBLVolumeRefraction( const in vec3 n, const in vec3 v, const in float roughness, const in vec3 diffuseColor,
		const in vec3 specularColor, const in float specularF90, const in vec3 position, const in mat4 modelMatrix,
		const in mat4 viewMatrix, const in mat4 projMatrix, const in float dispersion, const in float ior, const in float thickness,
		const in vec3 attenuationColor, const in float attenuationDistance ) {
		vec4 transmittedLight;
		vec3 transmittance;
		#ifdef USE_DISPERSION
			float halfSpread = ( ior - 1.0 ) * 0.025 * dispersion;
			vec3 iors = vec3( ior - halfSpread, ior, ior + halfSpread );
			for ( int i = 0; i < 3; i ++ ) {
				vec3 transmissionRay = getVolumeTransmissionRay( n, v, thickness, iors[ i ], modelMatrix );
				vec3 refractedRayExit = position + transmissionRay;
		
				vec4 ndcPos = projMatrix * viewMatrix * vec4( refractedRayExit, 1.0 );
				vec2 refractionCoords = ndcPos.xy / ndcPos.w;
				refractionCoords += 1.0;
				refractionCoords /= 2.0;
		
				vec4 transmissionSample = getTransmissionSample( refractionCoords, roughness, iors[ i ] );
				transmittedLight[ i ] = transmissionSample[ i ];
				transmittedLight.a += transmissionSample.a;
				transmittance[ i ] = diffuseColor[ i ] * volumeAttenuation( length( transmissionRay ), attenuationColor, attenuationDistance )[ i ];
			}
			transmittedLight.a /= 3.0;
		
		#else
		
			vec3 transmissionRay = getVolumeTransmissionRay( n, v, thickness, ior, modelMatrix );
			vec3 refractedRayExit = position + transmissionRay;
			vec4 ndcPos = projMatrix * viewMatrix * vec4( refractedRayExit, 1.0 );
			vec2 refractionCoords = ndcPos.xy / ndcPos.w;
			refractionCoords += 1.0;
			refractionCoords /= 2.0;
			transmittedLight = getTransmissionSample( refractionCoords, roughness, ior );
			transmittance = diffuseColor * volumeAttenuation( length( transmissionRay ), attenuationColor, attenuationDistance );
		
		#endif
		vec3 attenuatedColor = transmittance * transmittedLight.rgb;
		vec3 F = EnvironmentBRDF( n, v, specularColor, specularF90, roughness );
		float transmittanceFactor = ( transmittance.r + transmittance.g + transmittance.b ) / 3.0;
		return vec4( ( 1.0 - F ) * attenuatedColor, 1.0 - ( 1.0 - transmittedLight.a ) * transmittanceFactor );
	}
#endif`,K0=`#if defined( USE_UV ) || defined( USE_ANISOTROPY )
	varying vec2 vUv;
#endif
#ifdef USE_MAP
	varying vec2 vMapUv;
#endif
#ifdef USE_ALPHAMAP
	varying vec2 vAlphaMapUv;
#endif
#ifdef USE_LIGHTMAP
	varying vec2 vLightMapUv;
#endif
#ifdef USE_AOMAP
	varying vec2 vAoMapUv;
#endif
#ifdef USE_BUMPMAP
	varying vec2 vBumpMapUv;
#endif
#ifdef USE_NORMALMAP
	varying vec2 vNormalMapUv;
#endif
#ifdef USE_EMISSIVEMAP
	varying vec2 vEmissiveMapUv;
#endif
#ifdef USE_METALNESSMAP
	varying vec2 vMetalnessMapUv;
#endif
#ifdef USE_ROUGHNESSMAP
	varying vec2 vRoughnessMapUv;
#endif
#ifdef USE_ANISOTROPYMAP
	varying vec2 vAnisotropyMapUv;
#endif
#ifdef USE_CLEARCOATMAP
	varying vec2 vClearcoatMapUv;
#endif
#ifdef USE_CLEARCOAT_NORMALMAP
	varying vec2 vClearcoatNormalMapUv;
#endif
#ifdef USE_CLEARCOAT_ROUGHNESSMAP
	varying vec2 vClearcoatRoughnessMapUv;
#endif
#ifdef USE_IRIDESCENCEMAP
	varying vec2 vIridescenceMapUv;
#endif
#ifdef USE_IRIDESCENCE_THICKNESSMAP
	varying vec2 vIridescenceThicknessMapUv;
#endif
#ifdef USE_SHEEN_COLORMAP
	varying vec2 vSheenColorMapUv;
#endif
#ifdef USE_SHEEN_ROUGHNESSMAP
	varying vec2 vSheenRoughnessMapUv;
#endif
#ifdef USE_SPECULARMAP
	varying vec2 vSpecularMapUv;
#endif
#ifdef USE_SPECULAR_COLORMAP
	varying vec2 vSpecularColorMapUv;
#endif
#ifdef USE_SPECULAR_INTENSITYMAP
	varying vec2 vSpecularIntensityMapUv;
#endif
#ifdef USE_TRANSMISSIONMAP
	uniform mat3 transmissionMapTransform;
	varying vec2 vTransmissionMapUv;
#endif
#ifdef USE_THICKNESSMAP
	uniform mat3 thicknessMapTransform;
	varying vec2 vThicknessMapUv;
#endif`,Z0=`#if defined( USE_UV ) || defined( USE_ANISOTROPY )
	varying vec2 vUv;
#endif
#ifdef USE_MAP
	uniform mat3 mapTransform;
	varying vec2 vMapUv;
#endif
#ifdef USE_ALPHAMAP
	uniform mat3 alphaMapTransform;
	varying vec2 vAlphaMapUv;
#endif
#ifdef USE_LIGHTMAP
	uniform mat3 lightMapTransform;
	varying vec2 vLightMapUv;
#endif
#ifdef USE_AOMAP
	uniform mat3 aoMapTransform;
	varying vec2 vAoMapUv;
#endif
#ifdef USE_BUMPMAP
	uniform mat3 bumpMapTransform;
	varying vec2 vBumpMapUv;
#endif
#ifdef USE_NORMALMAP
	uniform mat3 normalMapTransform;
	varying vec2 vNormalMapUv;
#endif
#ifdef USE_DISPLACEMENTMAP
	uniform mat3 displacementMapTransform;
	varying vec2 vDisplacementMapUv;
#endif
#ifdef USE_EMISSIVEMAP
	uniform mat3 emissiveMapTransform;
	varying vec2 vEmissiveMapUv;
#endif
#ifdef USE_METALNESSMAP
	uniform mat3 metalnessMapTransform;
	varying vec2 vMetalnessMapUv;
#endif
#ifdef USE_ROUGHNESSMAP
	uniform mat3 roughnessMapTransform;
	varying vec2 vRoughnessMapUv;
#endif
#ifdef USE_ANISOTROPYMAP
	uniform mat3 anisotropyMapTransform;
	varying vec2 vAnisotropyMapUv;
#endif
#ifdef USE_CLEARCOATMAP
	uniform mat3 clearcoatMapTransform;
	varying vec2 vClearcoatMapUv;
#endif
#ifdef USE_CLEARCOAT_NORMALMAP
	uniform mat3 clearcoatNormalMapTransform;
	varying vec2 vClearcoatNormalMapUv;
#endif
#ifdef USE_CLEARCOAT_ROUGHNESSMAP
	uniform mat3 clearcoatRoughnessMapTransform;
	varying vec2 vClearcoatRoughnessMapUv;
#endif
#ifdef USE_SHEEN_COLORMAP
	uniform mat3 sheenColorMapTransform;
	varying vec2 vSheenColorMapUv;
#endif
#ifdef USE_SHEEN_ROUGHNESSMAP
	uniform mat3 sheenRoughnessMapTransform;
	varying vec2 vSheenRoughnessMapUv;
#endif
#ifdef USE_IRIDESCENCEMAP
	uniform mat3 iridescenceMapTransform;
	varying vec2 vIridescenceMapUv;
#endif
#ifdef USE_IRIDESCENCE_THICKNESSMAP
	uniform mat3 iridescenceThicknessMapTransform;
	varying vec2 vIridescenceThicknessMapUv;
#endif
#ifdef USE_SPECULARMAP
	uniform mat3 specularMapTransform;
	varying vec2 vSpecularMapUv;
#endif
#ifdef USE_SPECULAR_COLORMAP
	uniform mat3 specularColorMapTransform;
	varying vec2 vSpecularColorMapUv;
#endif
#ifdef USE_SPECULAR_INTENSITYMAP
	uniform mat3 specularIntensityMapTransform;
	varying vec2 vSpecularIntensityMapUv;
#endif
#ifdef USE_TRANSMISSIONMAP
	uniform mat3 transmissionMapTransform;
	varying vec2 vTransmissionMapUv;
#endif
#ifdef USE_THICKNESSMAP
	uniform mat3 thicknessMapTransform;
	varying vec2 vThicknessMapUv;
#endif`,J0=`#if defined( USE_UV ) || defined( USE_ANISOTROPY )
	vUv = vec3( uv, 1 ).xy;
#endif
#ifdef USE_MAP
	vMapUv = ( mapTransform * vec3( MAP_UV, 1 ) ).xy;
#endif
#ifdef USE_ALPHAMAP
	vAlphaMapUv = ( alphaMapTransform * vec3( ALPHAMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_LIGHTMAP
	vLightMapUv = ( lightMapTransform * vec3( LIGHTMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_AOMAP
	vAoMapUv = ( aoMapTransform * vec3( AOMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_BUMPMAP
	vBumpMapUv = ( bumpMapTransform * vec3( BUMPMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_NORMALMAP
	vNormalMapUv = ( normalMapTransform * vec3( NORMALMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_DISPLACEMENTMAP
	vDisplacementMapUv = ( displacementMapTransform * vec3( DISPLACEMENTMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_EMISSIVEMAP
	vEmissiveMapUv = ( emissiveMapTransform * vec3( EMISSIVEMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_METALNESSMAP
	vMetalnessMapUv = ( metalnessMapTransform * vec3( METALNESSMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_ROUGHNESSMAP
	vRoughnessMapUv = ( roughnessMapTransform * vec3( ROUGHNESSMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_ANISOTROPYMAP
	vAnisotropyMapUv = ( anisotropyMapTransform * vec3( ANISOTROPYMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_CLEARCOATMAP
	vClearcoatMapUv = ( clearcoatMapTransform * vec3( CLEARCOATMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_CLEARCOAT_NORMALMAP
	vClearcoatNormalMapUv = ( clearcoatNormalMapTransform * vec3( CLEARCOAT_NORMALMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_CLEARCOAT_ROUGHNESSMAP
	vClearcoatRoughnessMapUv = ( clearcoatRoughnessMapTransform * vec3( CLEARCOAT_ROUGHNESSMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_IRIDESCENCEMAP
	vIridescenceMapUv = ( iridescenceMapTransform * vec3( IRIDESCENCEMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_IRIDESCENCE_THICKNESSMAP
	vIridescenceThicknessMapUv = ( iridescenceThicknessMapTransform * vec3( IRIDESCENCE_THICKNESSMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_SHEEN_COLORMAP
	vSheenColorMapUv = ( sheenColorMapTransform * vec3( SHEEN_COLORMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_SHEEN_ROUGHNESSMAP
	vSheenRoughnessMapUv = ( sheenRoughnessMapTransform * vec3( SHEEN_ROUGHNESSMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_SPECULARMAP
	vSpecularMapUv = ( specularMapTransform * vec3( SPECULARMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_SPECULAR_COLORMAP
	vSpecularColorMapUv = ( specularColorMapTransform * vec3( SPECULAR_COLORMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_SPECULAR_INTENSITYMAP
	vSpecularIntensityMapUv = ( specularIntensityMapTransform * vec3( SPECULAR_INTENSITYMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_TRANSMISSIONMAP
	vTransmissionMapUv = ( transmissionMapTransform * vec3( TRANSMISSIONMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_THICKNESSMAP
	vThicknessMapUv = ( thicknessMapTransform * vec3( THICKNESSMAP_UV, 1 ) ).xy;
#endif`,$0=`#if defined( USE_ENVMAP ) || defined( DISTANCE ) || defined ( USE_SHADOWMAP ) || defined ( USE_TRANSMISSION ) || NUM_SPOT_LIGHT_COORDS > 0
	vec4 worldPosition = vec4( transformed, 1.0 );
	#ifdef USE_BATCHING
		worldPosition = batchingMatrix * worldPosition;
	#endif
	#ifdef USE_INSTANCING
		worldPosition = instanceMatrix * worldPosition;
	#endif
	worldPosition = modelMatrix * worldPosition;
#endif`;const Q0=`varying vec2 vUv;
uniform mat3 uvTransform;
void main() {
	vUv = ( uvTransform * vec3( uv, 1 ) ).xy;
	gl_Position = vec4( position.xy, 1.0, 1.0 );
}`,ep=`uniform sampler2D t2D;
uniform float backgroundIntensity;
varying vec2 vUv;
void main() {
	vec4 texColor = texture2D( t2D, vUv );
	#ifdef DECODE_VIDEO_TEXTURE
		texColor = vec4( mix( pow( texColor.rgb * 0.9478672986 + vec3( 0.0521327014 ), vec3( 2.4 ) ), texColor.rgb * 0.0773993808, vec3( lessThanEqual( texColor.rgb, vec3( 0.04045 ) ) ) ), texColor.w );
	#endif
	texColor.rgb *= backgroundIntensity;
	gl_FragColor = texColor;
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
}`,tp=`varying vec3 vWorldDirection;
#include <common>
void main() {
	vWorldDirection = transformDirection( position, modelMatrix );
	#include <begin_vertex>
	#include <project_vertex>
	gl_Position.z = gl_Position.w;
}`,np=`#ifdef ENVMAP_TYPE_CUBE
	uniform samplerCube envMap;
#elif defined( ENVMAP_TYPE_CUBE_UV )
	uniform sampler2D envMap;
#endif
uniform float flipEnvMap;
uniform float backgroundBlurriness;
uniform float backgroundIntensity;
uniform mat3 backgroundRotation;
varying vec3 vWorldDirection;
#include <cube_uv_reflection_fragment>
void main() {
	#ifdef ENVMAP_TYPE_CUBE
		vec4 texColor = textureCube( envMap, backgroundRotation * vec3( flipEnvMap * vWorldDirection.x, vWorldDirection.yz ) );
	#elif defined( ENVMAP_TYPE_CUBE_UV )
		vec4 texColor = textureCubeUV( envMap, backgroundRotation * vWorldDirection, backgroundBlurriness );
	#else
		vec4 texColor = vec4( 0.0, 0.0, 0.0, 1.0 );
	#endif
	texColor.rgb *= backgroundIntensity;
	gl_FragColor = texColor;
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
}`,ip=`varying vec3 vWorldDirection;
#include <common>
void main() {
	vWorldDirection = transformDirection( position, modelMatrix );
	#include <begin_vertex>
	#include <project_vertex>
	gl_Position.z = gl_Position.w;
}`,sp=`uniform samplerCube tCube;
uniform float tFlip;
uniform float opacity;
varying vec3 vWorldDirection;
void main() {
	vec4 texColor = textureCube( tCube, vec3( tFlip * vWorldDirection.x, vWorldDirection.yz ) );
	gl_FragColor = texColor;
	gl_FragColor.a *= opacity;
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
}`,rp=`#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
varying vec2 vHighPrecisionZW;
void main() {
	#include <uv_vertex>
	#include <batching_vertex>
	#include <skinbase_vertex>
	#include <morphinstance_vertex>
	#ifdef USE_DISPLACEMENTMAP
		#include <beginnormal_vertex>
		#include <morphnormal_vertex>
		#include <skinnormal_vertex>
	#endif
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	vHighPrecisionZW = gl_Position.zw;
}`,op=`#if DEPTH_PACKING == 3200
	uniform float opacity;
#endif
#include <common>
#include <packing>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
varying vec2 vHighPrecisionZW;
void main() {
	vec4 diffuseColor = vec4( 1.0 );
	#include <clipping_planes_fragment>
	#if DEPTH_PACKING == 3200
		diffuseColor.a = opacity;
	#endif
	#include <map_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <logdepthbuf_fragment>
	float fragCoordZ = 0.5 * vHighPrecisionZW[0] / vHighPrecisionZW[1] + 0.5;
	#if DEPTH_PACKING == 3200
		gl_FragColor = vec4( vec3( 1.0 - fragCoordZ ), opacity );
	#elif DEPTH_PACKING == 3201
		gl_FragColor = packDepthToRGBA( fragCoordZ );
	#elif DEPTH_PACKING == 3202
		gl_FragColor = vec4( packDepthToRGB( fragCoordZ ), 1.0 );
	#elif DEPTH_PACKING == 3203
		gl_FragColor = vec4( packDepthToRG( fragCoordZ ), 0.0, 1.0 );
	#endif
}`,ap=`#define DISTANCE
varying vec3 vWorldPosition;
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <batching_vertex>
	#include <skinbase_vertex>
	#include <morphinstance_vertex>
	#ifdef USE_DISPLACEMENTMAP
		#include <beginnormal_vertex>
		#include <morphnormal_vertex>
		#include <skinnormal_vertex>
	#endif
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <worldpos_vertex>
	#include <clipping_planes_vertex>
	vWorldPosition = worldPosition.xyz;
}`,lp=`#define DISTANCE
uniform vec3 referencePosition;
uniform float nearDistance;
uniform float farDistance;
varying vec3 vWorldPosition;
#include <common>
#include <packing>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <clipping_planes_pars_fragment>
void main () {
	vec4 diffuseColor = vec4( 1.0 );
	#include <clipping_planes_fragment>
	#include <map_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	float dist = length( vWorldPosition - referencePosition );
	dist = ( dist - nearDistance ) / ( farDistance - nearDistance );
	dist = saturate( dist );
	gl_FragColor = packDepthToRGBA( dist );
}`,cp=`varying vec3 vWorldDirection;
#include <common>
void main() {
	vWorldDirection = transformDirection( position, modelMatrix );
	#include <begin_vertex>
	#include <project_vertex>
}`,hp=`uniform sampler2D tEquirect;
varying vec3 vWorldDirection;
#include <common>
void main() {
	vec3 direction = normalize( vWorldDirection );
	vec2 sampleUV = equirectUv( direction );
	gl_FragColor = texture2D( tEquirect, sampleUV );
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
}`,up=`uniform float scale;
attribute float lineDistance;
varying float vLineDistance;
#include <common>
#include <uv_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <morphtarget_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	vLineDistance = scale * lineDistance;
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	#include <fog_vertex>
}`,dp=`uniform vec3 diffuse;
uniform float opacity;
uniform float dashSize;
uniform float totalSize;
varying float vLineDistance;
#include <common>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <fog_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	if ( mod( vLineDistance, totalSize ) > dashSize ) {
		discard;
	}
	vec3 outgoingLight = vec3( 0.0 );
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	outgoingLight = diffuseColor.rgb;
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
}`,fp=`#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <envmap_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#if defined ( USE_ENVMAP ) || defined ( USE_SKINNING )
		#include <beginnormal_vertex>
		#include <morphnormal_vertex>
		#include <skinbase_vertex>
		#include <skinnormal_vertex>
		#include <defaultnormal_vertex>
	#endif
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	#include <worldpos_vertex>
	#include <envmap_vertex>
	#include <fog_vertex>
}`,pp=`uniform vec3 diffuse;
uniform float opacity;
#ifndef FLAT_SHADED
	varying vec3 vNormal;
#endif
#include <common>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <aomap_pars_fragment>
#include <lightmap_pars_fragment>
#include <envmap_common_pars_fragment>
#include <envmap_pars_fragment>
#include <fog_pars_fragment>
#include <specularmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <specularmap_fragment>
	ReflectedLight reflectedLight = ReflectedLight( vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ) );
	#ifdef USE_LIGHTMAP
		vec4 lightMapTexel = texture2D( lightMap, vLightMapUv );
		reflectedLight.indirectDiffuse += lightMapTexel.rgb * lightMapIntensity * RECIPROCAL_PI;
	#else
		reflectedLight.indirectDiffuse += vec3( 1.0 );
	#endif
	#include <aomap_fragment>
	reflectedLight.indirectDiffuse *= diffuseColor.rgb;
	vec3 outgoingLight = reflectedLight.indirectDiffuse;
	#include <envmap_fragment>
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,mp=`#define LAMBERT
varying vec3 vViewPosition;
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <envmap_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <shadowmap_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	vViewPosition = - mvPosition.xyz;
	#include <worldpos_vertex>
	#include <envmap_vertex>
	#include <shadowmap_vertex>
	#include <fog_vertex>
}`,gp=`#define LAMBERT
uniform vec3 diffuse;
uniform vec3 emissive;
uniform float opacity;
#include <common>
#include <packing>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <aomap_pars_fragment>
#include <lightmap_pars_fragment>
#include <emissivemap_pars_fragment>
#include <envmap_common_pars_fragment>
#include <envmap_pars_fragment>
#include <fog_pars_fragment>
#include <bsdfs>
#include <lights_pars_begin>
#include <normal_pars_fragment>
#include <lights_lambert_pars_fragment>
#include <shadowmap_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <specularmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	ReflectedLight reflectedLight = ReflectedLight( vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ) );
	vec3 totalEmissiveRadiance = emissive;
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <specularmap_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	#include <emissivemap_fragment>
	#include <lights_lambert_fragment>
	#include <lights_fragment_begin>
	#include <lights_fragment_maps>
	#include <lights_fragment_end>
	#include <aomap_fragment>
	vec3 outgoingLight = reflectedLight.directDiffuse + reflectedLight.indirectDiffuse + totalEmissiveRadiance;
	#include <envmap_fragment>
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,vp=`#define MATCAP
varying vec3 vViewPosition;
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <color_pars_vertex>
#include <displacementmap_pars_vertex>
#include <fog_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	#include <fog_vertex>
	vViewPosition = - mvPosition.xyz;
}`,xp=`#define MATCAP
uniform vec3 diffuse;
uniform float opacity;
uniform sampler2D matcap;
varying vec3 vViewPosition;
#include <common>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <fog_pars_fragment>
#include <normal_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	vec3 viewDir = normalize( vViewPosition );
	vec3 x = normalize( vec3( viewDir.z, 0.0, - viewDir.x ) );
	vec3 y = cross( viewDir, x );
	vec2 uv = vec2( dot( x, normal ), dot( y, normal ) ) * 0.495 + 0.5;
	#ifdef USE_MATCAP
		vec4 matcapColor = texture2D( matcap, uv );
	#else
		vec4 matcapColor = vec4( vec3( mix( 0.2, 0.8, uv.y ) ), 1.0 );
	#endif
	vec3 outgoingLight = diffuseColor.rgb * matcapColor.rgb;
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,_p=`#define NORMAL
#if defined( FLAT_SHADED ) || defined( USE_BUMPMAP ) || defined( USE_NORMALMAP_TANGENTSPACE )
	varying vec3 vViewPosition;
#endif
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphinstance_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
#if defined( FLAT_SHADED ) || defined( USE_BUMPMAP ) || defined( USE_NORMALMAP_TANGENTSPACE )
	vViewPosition = - mvPosition.xyz;
#endif
}`,yp=`#define NORMAL
uniform float opacity;
#if defined( FLAT_SHADED ) || defined( USE_BUMPMAP ) || defined( USE_NORMALMAP_TANGENTSPACE )
	varying vec3 vViewPosition;
#endif
#include <packing>
#include <uv_pars_fragment>
#include <normal_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( 0.0, 0.0, 0.0, opacity );
	#include <clipping_planes_fragment>
	#include <logdepthbuf_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	gl_FragColor = vec4( packNormalToRGB( normal ), diffuseColor.a );
	#ifdef OPAQUE
		gl_FragColor.a = 1.0;
	#endif
}`,Mp=`#define PHONG
varying vec3 vViewPosition;
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <envmap_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <shadowmap_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphinstance_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	vViewPosition = - mvPosition.xyz;
	#include <worldpos_vertex>
	#include <envmap_vertex>
	#include <shadowmap_vertex>
	#include <fog_vertex>
}`,bp=`#define PHONG
uniform vec3 diffuse;
uniform vec3 emissive;
uniform vec3 specular;
uniform float shininess;
uniform float opacity;
#include <common>
#include <packing>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <aomap_pars_fragment>
#include <lightmap_pars_fragment>
#include <emissivemap_pars_fragment>
#include <envmap_common_pars_fragment>
#include <envmap_pars_fragment>
#include <fog_pars_fragment>
#include <bsdfs>
#include <lights_pars_begin>
#include <normal_pars_fragment>
#include <lights_phong_pars_fragment>
#include <shadowmap_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <specularmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	ReflectedLight reflectedLight = ReflectedLight( vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ) );
	vec3 totalEmissiveRadiance = emissive;
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <specularmap_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	#include <emissivemap_fragment>
	#include <lights_phong_fragment>
	#include <lights_fragment_begin>
	#include <lights_fragment_maps>
	#include <lights_fragment_end>
	#include <aomap_fragment>
	vec3 outgoingLight = reflectedLight.directDiffuse + reflectedLight.indirectDiffuse + reflectedLight.directSpecular + reflectedLight.indirectSpecular + totalEmissiveRadiance;
	#include <envmap_fragment>
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,wp=`#define STANDARD
varying vec3 vViewPosition;
#ifdef USE_TRANSMISSION
	varying vec3 vWorldPosition;
#endif
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <shadowmap_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	vViewPosition = - mvPosition.xyz;
	#include <worldpos_vertex>
	#include <shadowmap_vertex>
	#include <fog_vertex>
#ifdef USE_TRANSMISSION
	vWorldPosition = worldPosition.xyz;
#endif
}`,Sp=`#define STANDARD
#ifdef PHYSICAL
	#define IOR
	#define USE_SPECULAR
#endif
uniform vec3 diffuse;
uniform vec3 emissive;
uniform float roughness;
uniform float metalness;
uniform float opacity;
#ifdef IOR
	uniform float ior;
#endif
#ifdef USE_SPECULAR
	uniform float specularIntensity;
	uniform vec3 specularColor;
	#ifdef USE_SPECULAR_COLORMAP
		uniform sampler2D specularColorMap;
	#endif
	#ifdef USE_SPECULAR_INTENSITYMAP
		uniform sampler2D specularIntensityMap;
	#endif
#endif
#ifdef USE_CLEARCOAT
	uniform float clearcoat;
	uniform float clearcoatRoughness;
#endif
#ifdef USE_DISPERSION
	uniform float dispersion;
#endif
#ifdef USE_IRIDESCENCE
	uniform float iridescence;
	uniform float iridescenceIOR;
	uniform float iridescenceThicknessMinimum;
	uniform float iridescenceThicknessMaximum;
#endif
#ifdef USE_SHEEN
	uniform vec3 sheenColor;
	uniform float sheenRoughness;
	#ifdef USE_SHEEN_COLORMAP
		uniform sampler2D sheenColorMap;
	#endif
	#ifdef USE_SHEEN_ROUGHNESSMAP
		uniform sampler2D sheenRoughnessMap;
	#endif
#endif
#ifdef USE_ANISOTROPY
	uniform vec2 anisotropyVector;
	#ifdef USE_ANISOTROPYMAP
		uniform sampler2D anisotropyMap;
	#endif
#endif
varying vec3 vViewPosition;
#include <common>
#include <packing>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <aomap_pars_fragment>
#include <lightmap_pars_fragment>
#include <emissivemap_pars_fragment>
#include <iridescence_fragment>
#include <cube_uv_reflection_fragment>
#include <envmap_common_pars_fragment>
#include <envmap_physical_pars_fragment>
#include <fog_pars_fragment>
#include <lights_pars_begin>
#include <normal_pars_fragment>
#include <lights_physical_pars_fragment>
#include <transmission_pars_fragment>
#include <shadowmap_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <clearcoat_pars_fragment>
#include <iridescence_pars_fragment>
#include <roughnessmap_pars_fragment>
#include <metalnessmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	ReflectedLight reflectedLight = ReflectedLight( vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ) );
	vec3 totalEmissiveRadiance = emissive;
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <roughnessmap_fragment>
	#include <metalnessmap_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	#include <clearcoat_normal_fragment_begin>
	#include <clearcoat_normal_fragment_maps>
	#include <emissivemap_fragment>
	#include <lights_physical_fragment>
	#include <lights_fragment_begin>
	#include <lights_fragment_maps>
	#include <lights_fragment_end>
	#include <aomap_fragment>
	vec3 totalDiffuse = reflectedLight.directDiffuse + reflectedLight.indirectDiffuse;
	vec3 totalSpecular = reflectedLight.directSpecular + reflectedLight.indirectSpecular;
	#include <transmission_fragment>
	vec3 outgoingLight = totalDiffuse + totalSpecular + totalEmissiveRadiance;
	#ifdef USE_SHEEN
		float sheenEnergyComp = 1.0 - 0.157 * max3( material.sheenColor );
		outgoingLight = outgoingLight * sheenEnergyComp + sheenSpecularDirect + sheenSpecularIndirect;
	#endif
	#ifdef USE_CLEARCOAT
		float dotNVcc = saturate( dot( geometryClearcoatNormal, geometryViewDir ) );
		vec3 Fcc = F_Schlick( material.clearcoatF0, material.clearcoatF90, dotNVcc );
		outgoingLight = outgoingLight * ( 1.0 - material.clearcoat * Fcc ) + ( clearcoatSpecularDirect + clearcoatSpecularIndirect ) * material.clearcoat;
	#endif
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,Tp=`#define TOON
varying vec3 vViewPosition;
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <shadowmap_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	vViewPosition = - mvPosition.xyz;
	#include <worldpos_vertex>
	#include <shadowmap_vertex>
	#include <fog_vertex>
}`,Ep=`#define TOON
uniform vec3 diffuse;
uniform vec3 emissive;
uniform float opacity;
#include <common>
#include <packing>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <aomap_pars_fragment>
#include <lightmap_pars_fragment>
#include <emissivemap_pars_fragment>
#include <gradientmap_pars_fragment>
#include <fog_pars_fragment>
#include <bsdfs>
#include <lights_pars_begin>
#include <normal_pars_fragment>
#include <lights_toon_pars_fragment>
#include <shadowmap_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	ReflectedLight reflectedLight = ReflectedLight( vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ) );
	vec3 totalEmissiveRadiance = emissive;
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	#include <emissivemap_fragment>
	#include <lights_toon_fragment>
	#include <lights_fragment_begin>
	#include <lights_fragment_maps>
	#include <lights_fragment_end>
	#include <aomap_fragment>
	vec3 outgoingLight = reflectedLight.directDiffuse + reflectedLight.indirectDiffuse + totalEmissiveRadiance;
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,Ap=`uniform float size;
uniform float scale;
#include <common>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <morphtarget_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
#ifdef USE_POINTS_UV
	varying vec2 vUv;
	uniform mat3 uvTransform;
#endif
void main() {
	#ifdef USE_POINTS_UV
		vUv = ( uvTransform * vec3( uv, 1 ) ).xy;
	#endif
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <project_vertex>
	gl_PointSize = size;
	#ifdef USE_SIZEATTENUATION
		bool isPerspective = isPerspectiveMatrix( projectionMatrix );
		if ( isPerspective ) gl_PointSize *= ( scale / - mvPosition.z );
	#endif
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	#include <worldpos_vertex>
	#include <fog_vertex>
}`,Cp=`uniform vec3 diffuse;
uniform float opacity;
#include <common>
#include <color_pars_fragment>
#include <map_particle_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <fog_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	vec3 outgoingLight = vec3( 0.0 );
	#include <logdepthbuf_fragment>
	#include <map_particle_fragment>
	#include <color_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	outgoingLight = diffuseColor.rgb;
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
}`,Pp=`#include <common>
#include <batching_pars_vertex>
#include <fog_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <shadowmap_pars_vertex>
void main() {
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphinstance_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <worldpos_vertex>
	#include <shadowmap_vertex>
	#include <fog_vertex>
}`,Rp=`uniform vec3 color;
uniform float opacity;
#include <common>
#include <packing>
#include <fog_pars_fragment>
#include <bsdfs>
#include <lights_pars_begin>
#include <logdepthbuf_pars_fragment>
#include <shadowmap_pars_fragment>
#include <shadowmask_pars_fragment>
void main() {
	#include <logdepthbuf_fragment>
	gl_FragColor = vec4( color, opacity * ( 1.0 - getShadowMask() ) );
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
}`,Dp=`uniform float rotation;
uniform vec2 center;
#include <common>
#include <uv_pars_vertex>
#include <fog_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	vec4 mvPosition = modelViewMatrix[ 3 ];
	vec2 scale = vec2( length( modelMatrix[ 0 ].xyz ), length( modelMatrix[ 1 ].xyz ) );
	#ifndef USE_SIZEATTENUATION
		bool isPerspective = isPerspectiveMatrix( projectionMatrix );
		if ( isPerspective ) scale *= - mvPosition.z;
	#endif
	vec2 alignedPosition = ( position.xy - ( center - vec2( 0.5 ) ) ) * scale;
	vec2 rotatedPosition;
	rotatedPosition.x = cos( rotation ) * alignedPosition.x - sin( rotation ) * alignedPosition.y;
	rotatedPosition.y = sin( rotation ) * alignedPosition.x + cos( rotation ) * alignedPosition.y;
	mvPosition.xy += rotatedPosition;
	gl_Position = projectionMatrix * mvPosition;
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	#include <fog_vertex>
}`,Ip=`uniform vec3 diffuse;
uniform float opacity;
#include <common>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <fog_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	vec3 outgoingLight = vec3( 0.0 );
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	outgoingLight = diffuseColor.rgb;
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
}`,Xe={alphahash_fragment:Qd,alphahash_pars_fragment:ef,alphamap_fragment:tf,alphamap_pars_fragment:nf,alphatest_fragment:sf,alphatest_pars_fragment:rf,aomap_fragment:of,aomap_pars_fragment:af,batching_pars_vertex:lf,batching_vertex:cf,begin_vertex:hf,beginnormal_vertex:uf,bsdfs:df,iridescence_fragment:ff,bumpmap_pars_fragment:pf,clipping_planes_fragment:mf,clipping_planes_pars_fragment:gf,clipping_planes_pars_vertex:vf,clipping_planes_vertex:xf,color_fragment:_f,color_pars_fragment:yf,color_pars_vertex:Mf,color_vertex:bf,common:wf,cube_uv_reflection_fragment:Sf,defaultnormal_vertex:Tf,displacementmap_pars_vertex:Ef,displacementmap_vertex:Af,emissivemap_fragment:Cf,emissivemap_pars_fragment:Pf,colorspace_fragment:Rf,colorspace_pars_fragment:Df,envmap_fragment:If,envmap_common_pars_fragment:Lf,envmap_pars_fragment:Nf,envmap_pars_vertex:Uf,envmap_physical_pars_fragment:Yf,envmap_vertex:Of,fog_vertex:Ff,fog_pars_vertex:zf,fog_fragment:kf,fog_pars_fragment:Bf,gradientmap_pars_fragment:Vf,lightmap_pars_fragment:Hf,lights_lambert_fragment:Gf,lights_lambert_pars_fragment:Wf,lights_pars_begin:Xf,lights_toon_fragment:qf,lights_toon_pars_fragment:jf,lights_phong_fragment:Kf,lights_phong_pars_fragment:Zf,lights_physical_fragment:Jf,lights_physical_pars_fragment:$f,lights_fragment_begin:Qf,lights_fragment_maps:e0,lights_fragment_end:t0,logdepthbuf_fragment:n0,logdepthbuf_pars_fragment:i0,logdepthbuf_pars_vertex:s0,logdepthbuf_vertex:r0,map_fragment:o0,map_pars_fragment:a0,map_particle_fragment:l0,map_particle_pars_fragment:c0,metalnessmap_fragment:h0,metalnessmap_pars_fragment:u0,morphinstance_vertex:d0,morphcolor_vertex:f0,morphnormal_vertex:p0,morphtarget_pars_vertex:m0,morphtarget_vertex:g0,normal_fragment_begin:v0,normal_fragment_maps:x0,normal_pars_fragment:_0,normal_pars_vertex:y0,normal_vertex:M0,normalmap_pars_fragment:b0,clearcoat_normal_fragment_begin:w0,clearcoat_normal_fragment_maps:S0,clearcoat_pars_fragment:T0,iridescence_pars_fragment:E0,opaque_fragment:A0,packing:C0,premultiplied_alpha_fragment:P0,project_vertex:R0,dithering_fragment:D0,dithering_pars_fragment:I0,roughnessmap_fragment:L0,roughnessmap_pars_fragment:N0,shadowmap_pars_fragment:U0,shadowmap_pars_vertex:O0,shadowmap_vertex:F0,shadowmask_pars_fragment:z0,skinbase_vertex:k0,skinning_pars_vertex:B0,skinning_vertex:V0,skinnormal_vertex:H0,specularmap_fragment:G0,specularmap_pars_fragment:W0,tonemapping_fragment:X0,tonemapping_pars_fragment:Y0,transmission_fragment:q0,transmission_pars_fragment:j0,uv_pars_fragment:K0,uv_pars_vertex:Z0,uv_vertex:J0,worldpos_vertex:$0,background_vert:Q0,background_frag:ep,backgroundCube_vert:tp,backgroundCube_frag:np,cube_vert:ip,cube_frag:sp,depth_vert:rp,depth_frag:op,distanceRGBA_vert:ap,distanceRGBA_frag:lp,equirect_vert:cp,equirect_frag:hp,linedashed_vert:up,linedashed_frag:dp,meshbasic_vert:fp,meshbasic_frag:pp,meshlambert_vert:mp,meshlambert_frag:gp,meshmatcap_vert:vp,meshmatcap_frag:xp,meshnormal_vert:_p,meshnormal_frag:yp,meshphong_vert:Mp,meshphong_frag:bp,meshphysical_vert:wp,meshphysical_frag:Sp,meshtoon_vert:Tp,meshtoon_frag:Ep,points_vert:Ap,points_frag:Cp,shadow_vert:Pp,shadow_frag:Rp,sprite_vert:Dp,sprite_frag:Ip},ge={common:{diffuse:{value:new Ne(16777215)},opacity:{value:1},map:{value:null},mapTransform:{value:new Ye},alphaMap:{value:null},alphaMapTransform:{value:new Ye},alphaTest:{value:0}},specularmap:{specularMap:{value:null},specularMapTransform:{value:new Ye}},envmap:{envMap:{value:null},envMapRotation:{value:new Ye},flipEnvMap:{value:-1},reflectivity:{value:1},ior:{value:1.5},refractionRatio:{value:.98}},aomap:{aoMap:{value:null},aoMapIntensity:{value:1},aoMapTransform:{value:new Ye}},lightmap:{lightMap:{value:null},lightMapIntensity:{value:1},lightMapTransform:{value:new Ye}},bumpmap:{bumpMap:{value:null},bumpMapTransform:{value:new Ye},bumpScale:{value:1}},normalmap:{normalMap:{value:null},normalMapTransform:{value:new Ye},normalScale:{value:new Q(1,1)}},displacementmap:{displacementMap:{value:null},displacementMapTransform:{value:new Ye},displacementScale:{value:1},displacementBias:{value:0}},emissivemap:{emissiveMap:{value:null},emissiveMapTransform:{value:new Ye}},metalnessmap:{metalnessMap:{value:null},metalnessMapTransform:{value:new Ye}},roughnessmap:{roughnessMap:{value:null},roughnessMapTransform:{value:new Ye}},gradientmap:{gradientMap:{value:null}},fog:{fogDensity:{value:25e-5},fogNear:{value:1},fogFar:{value:2e3},fogColor:{value:new Ne(16777215)}},lights:{ambientLightColor:{value:[]},lightProbe:{value:[]},directionalLights:{value:[],properties:{direction:{},color:{}}},directionalLightShadows:{value:[],properties:{shadowIntensity:1,shadowBias:{},shadowNormalBias:{},shadowRadius:{},shadowMapSize:{}}},directionalShadowMap:{value:[]},directionalShadowMatrix:{value:[]},spotLights:{value:[],properties:{color:{},position:{},direction:{},distance:{},coneCos:{},penumbraCos:{},decay:{}}},spotLightShadows:{value:[],properties:{shadowIntensity:1,shadowBias:{},shadowNormalBias:{},shadowRadius:{},shadowMapSize:{}}},spotLightMap:{value:[]},spotShadowMap:{value:[]},spotLightMatrix:{value:[]},pointLights:{value:[],properties:{color:{},position:{},decay:{},distance:{}}},pointLightShadows:{value:[],properties:{shadowIntensity:1,shadowBias:{},shadowNormalBias:{},shadowRadius:{},shadowMapSize:{},shadowCameraNear:{},shadowCameraFar:{}}},pointShadowMap:{value:[]},pointShadowMatrix:{value:[]},hemisphereLights:{value:[],properties:{direction:{},skyColor:{},groundColor:{}}},rectAreaLights:{value:[],properties:{color:{},position:{},width:{},height:{}}},ltc_1:{value:null},ltc_2:{value:null}},points:{diffuse:{value:new Ne(16777215)},opacity:{value:1},size:{value:1},scale:{value:1},map:{value:null},alphaMap:{value:null},alphaMapTransform:{value:new Ye},alphaTest:{value:0},uvTransform:{value:new Ye}},sprite:{diffuse:{value:new Ne(16777215)},opacity:{value:1},center:{value:new Q(.5,.5)},rotation:{value:0},map:{value:null},mapTransform:{value:new Ye},alphaMap:{value:null},alphaMapTransform:{value:new Ye},alphaTest:{value:0}}},Sn={basic:{uniforms:Xt([ge.common,ge.specularmap,ge.envmap,ge.aomap,ge.lightmap,ge.fog]),vertexShader:Xe.meshbasic_vert,fragmentShader:Xe.meshbasic_frag},lambert:{uniforms:Xt([ge.common,ge.specularmap,ge.envmap,ge.aomap,ge.lightmap,ge.emissivemap,ge.bumpmap,ge.normalmap,ge.displacementmap,ge.fog,ge.lights,{emissive:{value:new Ne(0)}}]),vertexShader:Xe.meshlambert_vert,fragmentShader:Xe.meshlambert_frag},phong:{uniforms:Xt([ge.common,ge.specularmap,ge.envmap,ge.aomap,ge.lightmap,ge.emissivemap,ge.bumpmap,ge.normalmap,ge.displacementmap,ge.fog,ge.lights,{emissive:{value:new Ne(0)},specular:{value:new Ne(1118481)},shininess:{value:30}}]),vertexShader:Xe.meshphong_vert,fragmentShader:Xe.meshphong_frag},standard:{uniforms:Xt([ge.common,ge.envmap,ge.aomap,ge.lightmap,ge.emissivemap,ge.bumpmap,ge.normalmap,ge.displacementmap,ge.roughnessmap,ge.metalnessmap,ge.fog,ge.lights,{emissive:{value:new Ne(0)},roughness:{value:1},metalness:{value:0},envMapIntensity:{value:1}}]),vertexShader:Xe.meshphysical_vert,fragmentShader:Xe.meshphysical_frag},toon:{uniforms:Xt([ge.common,ge.aomap,ge.lightmap,ge.emissivemap,ge.bumpmap,ge.normalmap,ge.displacementmap,ge.gradientmap,ge.fog,ge.lights,{emissive:{value:new Ne(0)}}]),vertexShader:Xe.meshtoon_vert,fragmentShader:Xe.meshtoon_frag},matcap:{uniforms:Xt([ge.common,ge.bumpmap,ge.normalmap,ge.displacementmap,ge.fog,{matcap:{value:null}}]),vertexShader:Xe.meshmatcap_vert,fragmentShader:Xe.meshmatcap_frag},points:{uniforms:Xt([ge.points,ge.fog]),vertexShader:Xe.points_vert,fragmentShader:Xe.points_frag},dashed:{uniforms:Xt([ge.common,ge.fog,{scale:{value:1},dashSize:{value:1},totalSize:{value:2}}]),vertexShader:Xe.linedashed_vert,fragmentShader:Xe.linedashed_frag},depth:{uniforms:Xt([ge.common,ge.displacementmap]),vertexShader:Xe.depth_vert,fragmentShader:Xe.depth_frag},normal:{uniforms:Xt([ge.common,ge.bumpmap,ge.normalmap,ge.displacementmap,{opacity:{value:1}}]),vertexShader:Xe.meshnormal_vert,fragmentShader:Xe.meshnormal_frag},sprite:{uniforms:Xt([ge.sprite,ge.fog]),vertexShader:Xe.sprite_vert,fragmentShader:Xe.sprite_frag},background:{uniforms:{uvTransform:{value:new Ye},t2D:{value:null},backgroundIntensity:{value:1}},vertexShader:Xe.background_vert,fragmentShader:Xe.background_frag},backgroundCube:{uniforms:{envMap:{value:null},flipEnvMap:{value:-1},backgroundBlurriness:{value:0},backgroundIntensity:{value:1},backgroundRotation:{value:new Ye}},vertexShader:Xe.backgroundCube_vert,fragmentShader:Xe.backgroundCube_frag},cube:{uniforms:{tCube:{value:null},tFlip:{value:-1},opacity:{value:1}},vertexShader:Xe.cube_vert,fragmentShader:Xe.cube_frag},equirect:{uniforms:{tEquirect:{value:null}},vertexShader:Xe.equirect_vert,fragmentShader:Xe.equirect_frag},distanceRGBA:{uniforms:Xt([ge.common,ge.displacementmap,{referencePosition:{value:new w},nearDistance:{value:1},farDistance:{value:1e3}}]),vertexShader:Xe.distanceRGBA_vert,fragmentShader:Xe.distanceRGBA_frag},shadow:{uniforms:Xt([ge.lights,ge.fog,{color:{value:new Ne(0)},opacity:{value:1}}]),vertexShader:Xe.shadow_vert,fragmentShader:Xe.shadow_frag}};Sn.physical={uniforms:Xt([Sn.standard.uniforms,{clearcoat:{value:0},clearcoatMap:{value:null},clearcoatMapTransform:{value:new Ye},clearcoatNormalMap:{value:null},clearcoatNormalMapTransform:{value:new Ye},clearcoatNormalScale:{value:new Q(1,1)},clearcoatRoughness:{value:0},clearcoatRoughnessMap:{value:null},clearcoatRoughnessMapTransform:{value:new Ye},dispersion:{value:0},iridescence:{value:0},iridescenceMap:{value:null},iridescenceMapTransform:{value:new Ye},iridescenceIOR:{value:1.3},iridescenceThicknessMinimum:{value:100},iridescenceThicknessMaximum:{value:400},iridescenceThicknessMap:{value:null},iridescenceThicknessMapTransform:{value:new Ye},sheen:{value:0},sheenColor:{value:new Ne(0)},sheenColorMap:{value:null},sheenColorMapTransform:{value:new Ye},sheenRoughness:{value:1},sheenRoughnessMap:{value:null},sheenRoughnessMapTransform:{value:new Ye},transmission:{value:0},transmissionMap:{value:null},transmissionMapTransform:{value:new Ye},transmissionSamplerSize:{value:new Q},transmissionSamplerMap:{value:null},thickness:{value:0},thicknessMap:{value:null},thicknessMapTransform:{value:new Ye},attenuationDistance:{value:0},attenuationColor:{value:new Ne(0)},specularColor:{value:new Ne(1,1,1)},specularColorMap:{value:null},specularColorMapTransform:{value:new Ye},specularIntensity:{value:1},specularIntensityMap:{value:null},specularIntensityMapTransform:{value:new Ye},anisotropyVector:{value:new Q},anisotropyMap:{value:null},anisotropyMapTransform:{value:new Ye}}]),vertexShader:Xe.meshphysical_vert,fragmentShader:Xe.meshphysical_frag};const ar={r:0,b:0,g:0},li=new Yt,Lp=new Fe;function Np(s,e,t,n,i,r,o){const a=new Ne(0);let l=r===!0?0:1,c,h,u=null,d=0,f=null;function g(_){let v=_.isScene===!0?_.background:null;return v&&v.isTexture&&(v=(_.backgroundBlurriness>0?t:e).get(v)),v}function x(_){let v=!1;const M=g(_);M===null?m(a,l):M&&M.isColor&&(m(M,1),v=!0);const S=s.xr.getEnvironmentBlendMode();S==="additive"?n.buffers.color.setClear(0,0,0,1,o):S==="alpha-blend"&&n.buffers.color.setClear(0,0,0,0,o),(s.autoClear||v)&&(n.buffers.depth.setTest(!0),n.buffers.depth.setMask(!0),n.buffers.color.setMask(!0),s.clear(s.autoClearColor,s.autoClearDepth,s.autoClearStencil))}function p(_,v){const M=g(v);M&&(M.isCubeTexture||M.mapping===Xr)?(h===void 0&&(h=new ve(new lt(1,1,1),new gt({name:"BackgroundCubeMaterial",uniforms:is(Sn.backgroundCube.uniforms),vertexShader:Sn.backgroundCube.vertexShader,fragmentShader:Sn.backgroundCube.fragmentShader,side:Ht,depthTest:!1,depthWrite:!1,fog:!1})),h.geometry.deleteAttribute("normal"),h.geometry.deleteAttribute("uv"),h.onBeforeRender=function(S,E,C){this.matrixWorld.copyPosition(C.matrixWorld)},Object.defineProperty(h.material,"envMap",{get:function(){return this.uniforms.envMap.value}}),i.update(h)),li.copy(v.backgroundRotation),li.x*=-1,li.y*=-1,li.z*=-1,M.isCubeTexture&&M.isRenderTargetTexture===!1&&(li.y*=-1,li.z*=-1),h.material.uniforms.envMap.value=M,h.material.uniforms.flipEnvMap.value=M.isCubeTexture&&M.isRenderTargetTexture===!1?-1:1,h.material.uniforms.backgroundBlurriness.value=v.backgroundBlurriness,h.material.uniforms.backgroundIntensity.value=v.backgroundIntensity,h.material.uniforms.backgroundRotation.value.setFromMatrix4(Lp.makeRotationFromEuler(li)),h.material.toneMapped=nt.getTransfer(M.colorSpace)!==ut,(u!==M||d!==M.version||f!==s.toneMapping)&&(h.material.needsUpdate=!0,u=M,d=M.version,f=s.toneMapping),h.layers.enableAll(),_.unshift(h,h.geometry,h.material,0,0,null)):M&&M.isTexture&&(c===void 0&&(c=new ve(new Gt(2,2),new gt({name:"BackgroundMaterial",uniforms:is(Sn.background.uniforms),vertexShader:Sn.background.vertexShader,fragmentShader:Sn.background.fragmentShader,side:wn,depthTest:!1,depthWrite:!1,fog:!1})),c.geometry.deleteAttribute("normal"),Object.defineProperty(c.material,"map",{get:function(){return this.uniforms.t2D.value}}),i.update(c)),c.material.uniforms.t2D.value=M,c.material.uniforms.backgroundIntensity.value=v.backgroundIntensity,c.material.toneMapped=nt.getTransfer(M.colorSpace)!==ut,M.matrixAutoUpdate===!0&&M.updateMatrix(),c.material.uniforms.uvTransform.value.copy(M.matrix),(u!==M||d!==M.version||f!==s.toneMapping)&&(c.material.needsUpdate=!0,u=M,d=M.version,f=s.toneMapping),c.layers.enableAll(),_.unshift(c,c.geometry,c.material,0,0,null))}function m(_,v){_.getRGB(ar,Nh(s)),n.buffers.color.setClear(ar.r,ar.g,ar.b,v,o)}return{getClearColor:function(){return a},setClearColor:function(_,v=1){a.set(_),l=v,m(a,l)},getClearAlpha:function(){return l},setClearAlpha:function(_){l=_,m(a,l)},render:x,addToRenderList:p}}function Up(s,e){const t=s.getParameter(s.MAX_VERTEX_ATTRIBS),n={},i=d(null);let r=i,o=!1;function a(y,b,D,L,N){let B=!1;const k=u(L,D,b);r!==k&&(r=k,c(r.object)),B=f(y,L,D,N),B&&g(y,L,D,N),N!==null&&e.update(N,s.ELEMENT_ARRAY_BUFFER),(B||o)&&(o=!1,M(y,b,D,L),N!==null&&s.bindBuffer(s.ELEMENT_ARRAY_BUFFER,e.get(N).buffer))}function l(){return s.createVertexArray()}function c(y){return s.bindVertexArray(y)}function h(y){return s.deleteVertexArray(y)}function u(y,b,D){const L=D.wireframe===!0;let N=n[y.id];N===void 0&&(N={},n[y.id]=N);let B=N[b.id];B===void 0&&(B={},N[b.id]=B);let k=B[L];return k===void 0&&(k=d(l()),B[L]=k),k}function d(y){const b=[],D=[],L=[];for(let N=0;N<t;N++)b[N]=0,D[N]=0,L[N]=0;return{geometry:null,program:null,wireframe:!1,newAttributes:b,enabledAttributes:D,attributeDivisors:L,object:y,attributes:{},index:null}}function f(y,b,D,L){const N=r.attributes,B=b.attributes;let k=0;const q=D.getAttributes();for(const U in q)if(q[U].location>=0){const P=N[U];let O=B[U];if(O===void 0&&(U==="instanceMatrix"&&y.instanceMatrix&&(O=y.instanceMatrix),U==="instanceColor"&&y.instanceColor&&(O=y.instanceColor)),P===void 0||P.attribute!==O||O&&P.data!==O.data)return!0;k++}return r.attributesNum!==k||r.index!==L}function g(y,b,D,L){const N={},B=b.attributes;let k=0;const q=D.getAttributes();for(const U in q)if(q[U].location>=0){let P=B[U];P===void 0&&(U==="instanceMatrix"&&y.instanceMatrix&&(P=y.instanceMatrix),U==="instanceColor"&&y.instanceColor&&(P=y.instanceColor));const O={};O.attribute=P,P&&P.data&&(O.data=P.data),N[U]=O,k++}r.attributes=N,r.attributesNum=k,r.index=L}function x(){const y=r.newAttributes;for(let b=0,D=y.length;b<D;b++)y[b]=0}function p(y){m(y,0)}function m(y,b){const D=r.newAttributes,L=r.enabledAttributes,N=r.attributeDivisors;D[y]=1,L[y]===0&&(s.enableVertexAttribArray(y),L[y]=1),N[y]!==b&&(s.vertexAttribDivisor(y,b),N[y]=b)}function _(){const y=r.newAttributes,b=r.enabledAttributes;for(let D=0,L=b.length;D<L;D++)b[D]!==y[D]&&(s.disableVertexAttribArray(D),b[D]=0)}function v(y,b,D,L,N,B,k){k===!0?s.vertexAttribIPointer(y,b,D,N,B):s.vertexAttribPointer(y,b,D,L,N,B)}function M(y,b,D,L){x();const N=L.attributes,B=D.getAttributes(),k=b.defaultAttributeValues;for(const q in B){const U=B[q];if(U.location>=0){let V=N[q];if(V===void 0&&(q==="instanceMatrix"&&y.instanceMatrix&&(V=y.instanceMatrix),q==="instanceColor"&&y.instanceColor&&(V=y.instanceColor)),V!==void 0){const P=V.normalized,O=V.itemSize,H=e.get(V);if(H===void 0)continue;const Z=H.buffer,W=H.type,$=H.bytesPerElement,le=W===s.INT||W===s.UNSIGNED_INT||V.gpuType===Wa;if(V.isInterleavedBufferAttribute){const he=V.data,Ce=he.stride,Oe=V.offset;if(he.isInstancedInterleavedBuffer){for(let Ie=0;Ie<U.locationSize;Ie++)m(U.location+Ie,he.meshPerAttribute);y.isInstancedMesh!==!0&&L._maxInstanceCount===void 0&&(L._maxInstanceCount=he.meshPerAttribute*he.count)}else for(let Ie=0;Ie<U.locationSize;Ie++)p(U.location+Ie);s.bindBuffer(s.ARRAY_BUFFER,Z);for(let Ie=0;Ie<U.locationSize;Ie++)v(U.location+Ie,O/U.locationSize,W,P,Ce*$,(Oe+O/U.locationSize*Ie)*$,le)}else{if(V.isInstancedBufferAttribute){for(let he=0;he<U.locationSize;he++)m(U.location+he,V.meshPerAttribute);y.isInstancedMesh!==!0&&L._maxInstanceCount===void 0&&(L._maxInstanceCount=V.meshPerAttribute*V.count)}else for(let he=0;he<U.locationSize;he++)p(U.location+he);s.bindBuffer(s.ARRAY_BUFFER,Z);for(let he=0;he<U.locationSize;he++)v(U.location+he,O/U.locationSize,W,P,O*$,O/U.locationSize*he*$,le)}}else if(k!==void 0){const P=k[q];if(P!==void 0)switch(P.length){case 2:s.vertexAttrib2fv(U.location,P);break;case 3:s.vertexAttrib3fv(U.location,P);break;case 4:s.vertexAttrib4fv(U.location,P);break;default:s.vertexAttrib1fv(U.location,P)}}}}_()}function S(){z();for(const y in n){const b=n[y];for(const D in b){const L=b[D];for(const N in L)h(L[N].object),delete L[N];delete b[D]}delete n[y]}}function E(y){if(n[y.id]===void 0)return;const b=n[y.id];for(const D in b){const L=b[D];for(const N in L)h(L[N].object),delete L[N];delete b[D]}delete n[y.id]}function C(y){for(const b in n){const D=n[b];if(D[y.id]===void 0)continue;const L=D[y.id];for(const N in L)h(L[N].object),delete L[N];delete D[y.id]}}function z(){T(),o=!0,r!==i&&(r=i,c(r.object))}function T(){i.geometry=null,i.program=null,i.wireframe=!1}return{setup:a,reset:z,resetDefaultState:T,dispose:S,releaseStatesOfGeometry:E,releaseStatesOfProgram:C,initAttributes:x,enableAttribute:p,disableUnusedAttributes:_}}function Op(s,e,t){let n;function i(c){n=c}function r(c,h){s.drawArrays(n,c,h),t.update(h,n,1)}function o(c,h,u){u!==0&&(s.drawArraysInstanced(n,c,h,u),t.update(h,n,u))}function a(c,h,u){if(u===0)return;e.get("WEBGL_multi_draw").multiDrawArraysWEBGL(n,c,0,h,0,u);let f=0;for(let g=0;g<u;g++)f+=h[g];t.update(f,n,1)}function l(c,h,u,d){if(u===0)return;const f=e.get("WEBGL_multi_draw");if(f===null)for(let g=0;g<c.length;g++)o(c[g],h[g],d[g]);else{f.multiDrawArraysInstancedWEBGL(n,c,0,h,0,d,0,u);let g=0;for(let x=0;x<u;x++)g+=h[x];for(let x=0;x<d.length;x++)t.update(g,n,d[x])}}this.setMode=i,this.render=r,this.renderInstances=o,this.renderMultiDraw=a,this.renderMultiDrawInstances=l}function Fp(s,e,t,n){let i;function r(){if(i!==void 0)return i;if(e.has("EXT_texture_filter_anisotropic")===!0){const C=e.get("EXT_texture_filter_anisotropic");i=s.getParameter(C.MAX_TEXTURE_MAX_ANISOTROPY_EXT)}else i=0;return i}function o(C){return!(C!==sn&&n.convert(C)!==s.getParameter(s.IMPLEMENTATION_COLOR_READ_FORMAT))}function a(C){const z=C===bn&&(e.has("EXT_color_buffer_half_float")||e.has("EXT_color_buffer_float"));return!(C!==Vn&&n.convert(C)!==s.getParameter(s.IMPLEMENTATION_COLOR_READ_TYPE)&&C!==Tn&&!z)}function l(C){if(C==="highp"){if(s.getShaderPrecisionFormat(s.VERTEX_SHADER,s.HIGH_FLOAT).precision>0&&s.getShaderPrecisionFormat(s.FRAGMENT_SHADER,s.HIGH_FLOAT).precision>0)return"highp";C="mediump"}return C==="mediump"&&s.getShaderPrecisionFormat(s.VERTEX_SHADER,s.MEDIUM_FLOAT).precision>0&&s.getShaderPrecisionFormat(s.FRAGMENT_SHADER,s.MEDIUM_FLOAT).precision>0?"mediump":"lowp"}let c=t.precision!==void 0?t.precision:"highp";const h=l(c);h!==c&&(console.warn("THREE.WebGLRenderer:",c,"not supported, using",h,"instead."),c=h);const u=t.logarithmicDepthBuffer===!0,d=t.reverseDepthBuffer===!0&&e.has("EXT_clip_control");if(d===!0){const C=e.get("EXT_clip_control");C.clipControlEXT(C.LOWER_LEFT_EXT,C.ZERO_TO_ONE_EXT)}const f=s.getParameter(s.MAX_TEXTURE_IMAGE_UNITS),g=s.getParameter(s.MAX_VERTEX_TEXTURE_IMAGE_UNITS),x=s.getParameter(s.MAX_TEXTURE_SIZE),p=s.getParameter(s.MAX_CUBE_MAP_TEXTURE_SIZE),m=s.getParameter(s.MAX_VERTEX_ATTRIBS),_=s.getParameter(s.MAX_VERTEX_UNIFORM_VECTORS),v=s.getParameter(s.MAX_VARYING_VECTORS),M=s.getParameter(s.MAX_FRAGMENT_UNIFORM_VECTORS),S=g>0,E=s.getParameter(s.MAX_SAMPLES);return{isWebGL2:!0,getMaxAnisotropy:r,getMaxPrecision:l,textureFormatReadable:o,textureTypeReadable:a,precision:c,logarithmicDepthBuffer:u,reverseDepthBuffer:d,maxTextures:f,maxVertexTextures:g,maxTextureSize:x,maxCubemapSize:p,maxAttributes:m,maxVertexUniforms:_,maxVaryings:v,maxFragmentUniforms:M,vertexTextures:S,maxSamples:E}}function zp(s){const e=this;let t=null,n=0,i=!1,r=!1;const o=new Jn,a=new Ye,l={value:null,needsUpdate:!1};this.uniform=l,this.numPlanes=0,this.numIntersection=0,this.init=function(u,d){const f=u.length!==0||d||n!==0||i;return i=d,n=u.length,f},this.beginShadows=function(){r=!0,h(null)},this.endShadows=function(){r=!1},this.setGlobalState=function(u,d){t=h(u,d,0)},this.setState=function(u,d,f){const g=u.clippingPlanes,x=u.clipIntersection,p=u.clipShadows,m=s.get(u);if(!i||g===null||g.length===0||r&&!p)r?h(null):c();else{const _=r?0:n,v=_*4;let M=m.clippingState||null;l.value=M,M=h(g,d,v,f);for(let S=0;S!==v;++S)M[S]=t[S];m.clippingState=M,this.numIntersection=x?this.numPlanes:0,this.numPlanes+=_}};function c(){l.value!==t&&(l.value=t,l.needsUpdate=n>0),e.numPlanes=n,e.numIntersection=0}function h(u,d,f,g){const x=u!==null?u.length:0;let p=null;if(x!==0){if(p=l.value,g!==!0||p===null){const m=f+x*4,_=d.matrixWorldInverse;a.getNormalMatrix(_),(p===null||p.length<m)&&(p=new Float32Array(m));for(let v=0,M=f;v!==x;++v,M+=4)o.copy(u[v]).applyMatrix4(_,a),o.normal.toArray(p,M),p[M+3]=o.constant}l.value=p,l.needsUpdate=!0}return e.numPlanes=x,e.numIntersection=0,p}}function kp(s){let e=new WeakMap;function t(o,a){return a===Dr?o.mapping=$i:a===ta&&(o.mapping=Qi),o}function n(o){if(o&&o.isTexture){const a=o.mapping;if(a===Dr||a===ta)if(e.has(o)){const l=e.get(o).texture;return t(l,o.mapping)}else{const l=o.image;if(l&&l.height>0){const c=new Kd(l.height);return c.fromEquirectangularTexture(s,o),e.set(o,c),o.addEventListener("dispose",i),t(c.texture,o.mapping)}else return null}}return o}function i(o){const a=o.target;a.removeEventListener("dispose",i);const l=e.get(a);l!==void 0&&(e.delete(a),l.dispose())}function r(){e=new WeakMap}return{get:n,dispose:r}}class tl extends Uh{constructor(e=-1,t=1,n=1,i=-1,r=.1,o=2e3){super(),this.isOrthographicCamera=!0,this.type="OrthographicCamera",this.zoom=1,this.view=null,this.left=e,this.right=t,this.top=n,this.bottom=i,this.near=r,this.far=o,this.updateProjectionMatrix()}copy(e,t){return super.copy(e,t),this.left=e.left,this.right=e.right,this.top=e.top,this.bottom=e.bottom,this.near=e.near,this.far=e.far,this.zoom=e.zoom,this.view=e.view===null?null:Object.assign({},e.view),this}setViewOffset(e,t,n,i,r,o){this.view===null&&(this.view={enabled:!0,fullWidth:1,fullHeight:1,offsetX:0,offsetY:0,width:1,height:1}),this.view.enabled=!0,this.view.fullWidth=e,this.view.fullHeight=t,this.view.offsetX=n,this.view.offsetY=i,this.view.width=r,this.view.height=o,this.updateProjectionMatrix()}clearViewOffset(){this.view!==null&&(this.view.enabled=!1),this.updateProjectionMatrix()}updateProjectionMatrix(){const e=(this.right-this.left)/(2*this.zoom),t=(this.top-this.bottom)/(2*this.zoom),n=(this.right+this.left)/2,i=(this.top+this.bottom)/2;let r=n-e,o=n+e,a=i+t,l=i-t;if(this.view!==null&&this.view.enabled){const c=(this.right-this.left)/this.view.fullWidth/this.zoom,h=(this.top-this.bottom)/this.view.fullHeight/this.zoom;r+=c*this.view.offsetX,o=r+c*this.view.width,a-=h*this.view.offsetY,l=a-h*this.view.height}this.projectionMatrix.makeOrthographic(r,o,a,l,this.near,this.far,this.coordinateSystem),this.projectionMatrixInverse.copy(this.projectionMatrix).invert()}toJSON(e){const t=super.toJSON(e);return t.object.zoom=this.zoom,t.object.left=this.left,t.object.right=this.right,t.object.top=this.top,t.object.bottom=this.bottom,t.object.near=this.near,t.object.far=this.far,this.view!==null&&(t.object.view=Object.assign({},this.view)),t}}const Xi=4,jl=[.125,.215,.35,.446,.526,.582],di=20,Ao=new tl,Kl=new Ne;let Co=null,Po=0,Ro=0,Do=!1;const hi=(1+Math.sqrt(5))/2,ki=1/hi,Zl=[new w(-hi,ki,0),new w(hi,ki,0),new w(-ki,0,hi),new w(ki,0,hi),new w(0,hi,-ki),new w(0,hi,ki),new w(-1,1,-1),new w(1,1,-1),new w(-1,1,1),new w(1,1,1)];class Ra{constructor(e){this._renderer=e,this._pingPongRenderTarget=null,this._lodMax=0,this._cubeSize=0,this._lodPlanes=[],this._sizeLods=[],this._sigmas=[],this._blurMaterial=null,this._cubemapMaterial=null,this._equirectMaterial=null,this._compileMaterial(this._blurMaterial)}fromScene(e,t=0,n=.1,i=100){Co=this._renderer.getRenderTarget(),Po=this._renderer.getActiveCubeFace(),Ro=this._renderer.getActiveMipmapLevel(),Do=this._renderer.xr.enabled,this._renderer.xr.enabled=!1,this._setSize(256);const r=this._allocateTargets();return r.depthBuffer=!0,this._sceneToCubeUV(e,n,i,r),t>0&&this._blur(r,0,0,t),this._applyPMREM(r),this._cleanup(r),r}fromEquirectangular(e,t=null){return this._fromTexture(e,t)}fromCubemap(e,t=null){return this._fromTexture(e,t)}compileCubemapShader(){this._cubemapMaterial===null&&(this._cubemapMaterial=Ql(),this._compileMaterial(this._cubemapMaterial))}compileEquirectangularShader(){this._equirectMaterial===null&&(this._equirectMaterial=$l(),this._compileMaterial(this._equirectMaterial))}dispose(){this._dispose(),this._cubemapMaterial!==null&&this._cubemapMaterial.dispose(),this._equirectMaterial!==null&&this._equirectMaterial.dispose()}_setSize(e){this._lodMax=Math.floor(Math.log2(e)),this._cubeSize=Math.pow(2,this._lodMax)}_dispose(){this._blurMaterial!==null&&this._blurMaterial.dispose(),this._pingPongRenderTarget!==null&&this._pingPongRenderTarget.dispose();for(let e=0;e<this._lodPlanes.length;e++)this._lodPlanes[e].dispose()}_cleanup(e){this._renderer.setRenderTarget(Co,Po,Ro),this._renderer.xr.enabled=Do,e.scissorTest=!1,lr(e,0,0,e.width,e.height)}_fromTexture(e,t){e.mapping===$i||e.mapping===Qi?this._setSize(e.image.length===0?16:e.image[0].width||e.image[0].image.width):this._setSize(e.image.width/4),Co=this._renderer.getRenderTarget(),Po=this._renderer.getActiveCubeFace(),Ro=this._renderer.getActiveMipmapLevel(),Do=this._renderer.xr.enabled,this._renderer.xr.enabled=!1;const n=t||this._allocateTargets();return this._textureToCubeUV(e,n),this._applyPMREM(n),this._cleanup(n),n}_allocateTargets(){const e=3*Math.max(this._cubeSize,112),t=4*this._cubeSize,n={magFilter:Ct,minFilter:Ct,generateMipmaps:!1,type:bn,format:sn,colorSpace:Hn,depthBuffer:!1},i=Jl(e,t,n);if(this._pingPongRenderTarget===null||this._pingPongRenderTarget.width!==e||this._pingPongRenderTarget.height!==t){this._pingPongRenderTarget!==null&&this._dispose(),this._pingPongRenderTarget=Jl(e,t,n);const{_lodMax:r}=this;({sizeLods:this._sizeLods,lodPlanes:this._lodPlanes,sigmas:this._sigmas}=Bp(r)),this._blurMaterial=Vp(r,e,t)}return i}_compileMaterial(e){const t=new ve(this._lodPlanes[0],e);this._renderer.compile(t,Ao)}_sceneToCubeUV(e,t,n,i){const a=new Jt(90,1,t,n),l=[1,-1,1,1,1,1],c=[1,1,1,-1,-1,-1],h=this._renderer,u=h.autoClear,d=h.toneMapping;h.getClearColor(Kl),h.toneMapping=ei,h.autoClear=!1;const f=new Ge({name:"PMREM.Background",side:Ht,depthWrite:!1,depthTest:!1}),g=new ve(new lt,f);let x=!1;const p=e.background;p?p.isColor&&(f.color.copy(p),e.background=null,x=!0):(f.color.copy(Kl),x=!0);for(let m=0;m<6;m++){const _=m%3;_===0?(a.up.set(0,l[m],0),a.lookAt(c[m],0,0)):_===1?(a.up.set(0,0,l[m]),a.lookAt(0,c[m],0)):(a.up.set(0,l[m],0),a.lookAt(0,0,c[m]));const v=this._cubeSize;lr(i,_*v,m>2?v:0,v,v),h.setRenderTarget(i),x&&h.render(g,a),h.render(e,a)}g.geometry.dispose(),g.material.dispose(),h.toneMapping=d,h.autoClear=u,e.background=p}_textureToCubeUV(e,t){const n=this._renderer,i=e.mapping===$i||e.mapping===Qi;i?(this._cubemapMaterial===null&&(this._cubemapMaterial=Ql()),this._cubemapMaterial.uniforms.flipEnvMap.value=e.isRenderTargetTexture===!1?-1:1):this._equirectMaterial===null&&(this._equirectMaterial=$l());const r=i?this._cubemapMaterial:this._equirectMaterial,o=new ve(this._lodPlanes[0],r),a=r.uniforms;a.envMap.value=e;const l=this._cubeSize;lr(t,0,0,3*l,2*l),n.setRenderTarget(t),n.render(o,Ao)}_applyPMREM(e){const t=this._renderer,n=t.autoClear;t.autoClear=!1;const i=this._lodPlanes.length;for(let r=1;r<i;r++){const o=Math.sqrt(this._sigmas[r]*this._sigmas[r]-this._sigmas[r-1]*this._sigmas[r-1]),a=Zl[(i-r-1)%Zl.length];this._blur(e,r-1,r,o,a)}t.autoClear=n}_blur(e,t,n,i,r){const o=this._pingPongRenderTarget;this._halfBlur(e,o,t,n,i,"latitudinal",r),this._halfBlur(o,e,n,n,i,"longitudinal",r)}_halfBlur(e,t,n,i,r,o,a){const l=this._renderer,c=this._blurMaterial;o!=="latitudinal"&&o!=="longitudinal"&&console.error("blur direction must be either latitudinal or longitudinal!");const h=3,u=new ve(this._lodPlanes[i],c),d=c.uniforms,f=this._sizeLods[n]-1,g=isFinite(r)?Math.PI/(2*f):2*Math.PI/(2*di-1),x=r/g,p=isFinite(r)?1+Math.floor(h*x):di;p>di&&console.warn(`sigmaRadians, ${r}, is too large and will clip, as it requested ${p} samples when the maximum is set to ${di}`);const m=[];let _=0;for(let C=0;C<di;++C){const z=C/x,T=Math.exp(-z*z/2);m.push(T),C===0?_+=T:C<p&&(_+=2*T)}for(let C=0;C<m.length;C++)m[C]=m[C]/_;d.envMap.value=e.texture,d.samples.value=p,d.weights.value=m,d.latitudinal.value=o==="latitudinal",a&&(d.poleAxis.value=a);const{_lodMax:v}=this;d.dTheta.value=g,d.mipInt.value=v-n;const M=this._sizeLods[i],S=3*M*(i>v-Xi?i-v+Xi:0),E=4*(this._cubeSize-M);lr(t,S,E,3*M,2*M),l.setRenderTarget(t),l.render(u,Ao)}}function Bp(s){const e=[],t=[],n=[];let i=s;const r=s-Xi+1+jl.length;for(let o=0;o<r;o++){const a=Math.pow(2,i);t.push(a);let l=1/a;o>s-Xi?l=jl[o-s+Xi-1]:o===0&&(l=0),n.push(l);const c=1/(a-2),h=-c,u=1+c,d=[h,h,u,h,u,u,h,h,u,u,h,u],f=6,g=6,x=3,p=2,m=1,_=new Float32Array(x*g*f),v=new Float32Array(p*g*f),M=new Float32Array(m*g*f);for(let E=0;E<f;E++){const C=E%3*2/3-1,z=E>2?0:-1,T=[C,z,0,C+2/3,z,0,C+2/3,z+1,0,C,z,0,C+2/3,z+1,0,C,z+1,0];_.set(T,x*g*E),v.set(d,p*g*E);const y=[E,E,E,E,E,E];M.set(y,m*g*E)}const S=new je;S.setAttribute("position",new kt(_,x)),S.setAttribute("uv",new kt(v,p)),S.setAttribute("faceIndex",new kt(M,m)),e.push(S),i>Xi&&i--}return{lodPlanes:e,sizeLods:t,sigmas:n}}function Jl(s,e,t){const n=new un(s,e,t);return n.texture.mapping=Xr,n.texture.name="PMREM.cubeUv",n.scissorTest=!0,n}function lr(s,e,t,n,i){s.viewport.set(e,t,n,i),s.scissor.set(e,t,n,i)}function Vp(s,e,t){const n=new Float32Array(di),i=new w(0,1,0);return new gt({name:"SphericalGaussianBlur",defines:{n:di,CUBEUV_TEXEL_WIDTH:1/e,CUBEUV_TEXEL_HEIGHT:1/t,CUBEUV_MAX_MIP:`${s}.0`},uniforms:{envMap:{value:null},samples:{value:1},weights:{value:n},latitudinal:{value:!1},dTheta:{value:0},mipInt:{value:0},poleAxis:{value:i}},vertexShader:nl(),fragmentShader:`

			precision mediump float;
			precision mediump int;

			varying vec3 vOutputDirection;

			uniform sampler2D envMap;
			uniform int samples;
			uniform float weights[ n ];
			uniform bool latitudinal;
			uniform float dTheta;
			uniform float mipInt;
			uniform vec3 poleAxis;

			#define ENVMAP_TYPE_CUBE_UV
			#include <cube_uv_reflection_fragment>

			vec3 getSample( float theta, vec3 axis ) {

				float cosTheta = cos( theta );
				// Rodrigues' axis-angle rotation
				vec3 sampleDirection = vOutputDirection * cosTheta
					+ cross( axis, vOutputDirection ) * sin( theta )
					+ axis * dot( axis, vOutputDirection ) * ( 1.0 - cosTheta );

				return bilinearCubeUV( envMap, sampleDirection, mipInt );

			}

			void main() {

				vec3 axis = latitudinal ? poleAxis : cross( poleAxis, vOutputDirection );

				if ( all( equal( axis, vec3( 0.0 ) ) ) ) {

					axis = vec3( vOutputDirection.z, 0.0, - vOutputDirection.x );

				}

				axis = normalize( axis );

				gl_FragColor = vec4( 0.0, 0.0, 0.0, 1.0 );
				gl_FragColor.rgb += weights[ 0 ] * getSample( 0.0, axis );

				for ( int i = 1; i < n; i++ ) {

					if ( i >= samples ) {

						break;

					}

					float theta = dTheta * float( i );
					gl_FragColor.rgb += weights[ i ] * getSample( -1.0 * theta, axis );
					gl_FragColor.rgb += weights[ i ] * getSample( theta, axis );

				}

			}
		`,blending:kn,depthTest:!1,depthWrite:!1})}function $l(){return new gt({name:"EquirectangularToCubeUV",uniforms:{envMap:{value:null}},vertexShader:nl(),fragmentShader:`

			precision mediump float;
			precision mediump int;

			varying vec3 vOutputDirection;

			uniform sampler2D envMap;

			#include <common>

			void main() {

				vec3 outputDirection = normalize( vOutputDirection );
				vec2 uv = equirectUv( outputDirection );

				gl_FragColor = vec4( texture2D ( envMap, uv ).rgb, 1.0 );

			}
		`,blending:kn,depthTest:!1,depthWrite:!1})}function Ql(){return new gt({name:"CubemapToCubeUV",uniforms:{envMap:{value:null},flipEnvMap:{value:-1}},vertexShader:nl(),fragmentShader:`

			precision mediump float;
			precision mediump int;

			uniform float flipEnvMap;

			varying vec3 vOutputDirection;

			uniform samplerCube envMap;

			void main() {

				gl_FragColor = textureCube( envMap, vec3( flipEnvMap * vOutputDirection.x, vOutputDirection.yz ) );

			}
		`,blending:kn,depthTest:!1,depthWrite:!1})}function nl(){return`

		precision mediump float;
		precision mediump int;

		attribute float faceIndex;

		varying vec3 vOutputDirection;

		// RH coordinate system; PMREM face-indexing convention
		vec3 getDirection( vec2 uv, float face ) {

			uv = 2.0 * uv - 1.0;

			vec3 direction = vec3( uv, 1.0 );

			if ( face == 0.0 ) {

				direction = direction.zyx; // ( 1, v, u ) pos x

			} else if ( face == 1.0 ) {

				direction = direction.xzy;
				direction.xz *= -1.0; // ( -u, 1, -v ) pos y

			} else if ( face == 2.0 ) {

				direction.x *= -1.0; // ( -u, v, 1 ) pos z

			} else if ( face == 3.0 ) {

				direction = direction.zyx;
				direction.xz *= -1.0; // ( -1, v, -u ) neg x

			} else if ( face == 4.0 ) {

				direction = direction.xzy;
				direction.xy *= -1.0; // ( -u, -1, v ) neg y

			} else if ( face == 5.0 ) {

				direction.z *= -1.0; // ( u, v, -1 ) neg z

			}

			return direction;

		}

		void main() {

			vOutputDirection = getDirection( uv, faceIndex );
			gl_Position = vec4( position, 1.0 );

		}
	`}function Hp(s){let e=new WeakMap,t=null;function n(a){if(a&&a.isTexture){const l=a.mapping,c=l===Dr||l===ta,h=l===$i||l===Qi;if(c||h){let u=e.get(a);const d=u!==void 0?u.texture.pmremVersion:0;if(a.isRenderTargetTexture&&a.pmremVersion!==d)return t===null&&(t=new Ra(s)),u=c?t.fromEquirectangular(a,u):t.fromCubemap(a,u),u.texture.pmremVersion=a.pmremVersion,e.set(a,u),u.texture;if(u!==void 0)return u.texture;{const f=a.image;return c&&f&&f.height>0||h&&f&&i(f)?(t===null&&(t=new Ra(s)),u=c?t.fromEquirectangular(a):t.fromCubemap(a),u.texture.pmremVersion=a.pmremVersion,e.set(a,u),a.addEventListener("dispose",r),u.texture):null}}}return a}function i(a){let l=0;const c=6;for(let h=0;h<c;h++)a[h]!==void 0&&l++;return l===c}function r(a){const l=a.target;l.removeEventListener("dispose",r);const c=e.get(l);c!==void 0&&(e.delete(l),c.dispose())}function o(){e=new WeakMap,t!==null&&(t.dispose(),t=null)}return{get:n,dispose:o}}function Gp(s){const e={};function t(n){if(e[n]!==void 0)return e[n];let i;switch(n){case"WEBGL_depth_texture":i=s.getExtension("WEBGL_depth_texture")||s.getExtension("MOZ_WEBGL_depth_texture")||s.getExtension("WEBKIT_WEBGL_depth_texture");break;case"EXT_texture_filter_anisotropic":i=s.getExtension("EXT_texture_filter_anisotropic")||s.getExtension("MOZ_EXT_texture_filter_anisotropic")||s.getExtension("WEBKIT_EXT_texture_filter_anisotropic");break;case"WEBGL_compressed_texture_s3tc":i=s.getExtension("WEBGL_compressed_texture_s3tc")||s.getExtension("MOZ_WEBGL_compressed_texture_s3tc")||s.getExtension("WEBKIT_WEBGL_compressed_texture_s3tc");break;case"WEBGL_compressed_texture_pvrtc":i=s.getExtension("WEBGL_compressed_texture_pvrtc")||s.getExtension("WEBKIT_WEBGL_compressed_texture_pvrtc");break;default:i=s.getExtension(n)}return e[n]=i,i}return{has:function(n){return t(n)!==null},init:function(){t("EXT_color_buffer_float"),t("WEBGL_clip_cull_distance"),t("OES_texture_float_linear"),t("EXT_color_buffer_half_float"),t("WEBGL_multisampled_render_to_texture"),t("WEBGL_render_shared_exponent")},get:function(n){const i=t(n);return i===null&&Cr("THREE.WebGLRenderer: "+n+" extension not supported."),i}}}function Wp(s,e,t,n){const i={},r=new WeakMap;function o(u){const d=u.target;d.index!==null&&e.remove(d.index);for(const g in d.attributes)e.remove(d.attributes[g]);for(const g in d.morphAttributes){const x=d.morphAttributes[g];for(let p=0,m=x.length;p<m;p++)e.remove(x[p])}d.removeEventListener("dispose",o),delete i[d.id];const f=r.get(d);f&&(e.remove(f),r.delete(d)),n.releaseStatesOfGeometry(d),d.isInstancedBufferGeometry===!0&&delete d._maxInstanceCount,t.memory.geometries--}function a(u,d){return i[d.id]===!0||(d.addEventListener("dispose",o),i[d.id]=!0,t.memory.geometries++),d}function l(u){const d=u.attributes;for(const g in d)e.update(d[g],s.ARRAY_BUFFER);const f=u.morphAttributes;for(const g in f){const x=f[g];for(let p=0,m=x.length;p<m;p++)e.update(x[p],s.ARRAY_BUFFER)}}function c(u){const d=[],f=u.index,g=u.attributes.position;let x=0;if(f!==null){const _=f.array;x=f.version;for(let v=0,M=_.length;v<M;v+=3){const S=_[v+0],E=_[v+1],C=_[v+2];d.push(S,E,E,C,C,S)}}else if(g!==void 0){const _=g.array;x=g.version;for(let v=0,M=_.length/3-1;v<M;v+=3){const S=v+0,E=v+1,C=v+2;d.push(S,E,E,C,C,S)}}else return;const p=new(Ch(d)?Lh:Ih)(d,1);p.version=x;const m=r.get(u);m&&e.remove(m),r.set(u,p)}function h(u){const d=r.get(u);if(d){const f=u.index;f!==null&&d.version<f.version&&c(u)}else c(u);return r.get(u)}return{get:a,update:l,getWireframeAttribute:h}}function Xp(s,e,t){let n;function i(d){n=d}let r,o;function a(d){r=d.type,o=d.bytesPerElement}function l(d,f){s.drawElements(n,f,r,d*o),t.update(f,n,1)}function c(d,f,g){g!==0&&(s.drawElementsInstanced(n,f,r,d*o,g),t.update(f,n,g))}function h(d,f,g){if(g===0)return;e.get("WEBGL_multi_draw").multiDrawElementsWEBGL(n,f,0,r,d,0,g);let p=0;for(let m=0;m<g;m++)p+=f[m];t.update(p,n,1)}function u(d,f,g,x){if(g===0)return;const p=e.get("WEBGL_multi_draw");if(p===null)for(let m=0;m<d.length;m++)c(d[m]/o,f[m],x[m]);else{p.multiDrawElementsInstancedWEBGL(n,f,0,r,d,0,x,0,g);let m=0;for(let _=0;_<g;_++)m+=f[_];for(let _=0;_<x.length;_++)t.update(m,n,x[_])}}this.setMode=i,this.setIndex=a,this.render=l,this.renderInstances=c,this.renderMultiDraw=h,this.renderMultiDrawInstances=u}function Yp(s){const e={geometries:0,textures:0},t={frame:0,calls:0,triangles:0,points:0,lines:0};function n(r,o,a){switch(t.calls++,o){case s.TRIANGLES:t.triangles+=a*(r/3);break;case s.LINES:t.lines+=a*(r/2);break;case s.LINE_STRIP:t.lines+=a*(r-1);break;case s.LINE_LOOP:t.lines+=a*r;break;case s.POINTS:t.points+=a*r;break;default:console.error("THREE.WebGLInfo: Unknown draw mode:",o);break}}function i(){t.calls=0,t.triangles=0,t.points=0,t.lines=0}return{memory:e,render:t,programs:null,autoReset:!0,reset:i,update:n}}function qp(s,e,t){const n=new WeakMap,i=new ot;function r(o,a,l){const c=o.morphTargetInfluences,h=a.morphAttributes.position||a.morphAttributes.normal||a.morphAttributes.color,u=h!==void 0?h.length:0;let d=n.get(a);if(d===void 0||d.count!==u){let T=function(){C.dispose(),n.delete(a),a.removeEventListener("dispose",T)};d!==void 0&&d.texture.dispose();const f=a.morphAttributes.position!==void 0,g=a.morphAttributes.normal!==void 0,x=a.morphAttributes.color!==void 0,p=a.morphAttributes.position||[],m=a.morphAttributes.normal||[],_=a.morphAttributes.color||[];let v=0;f===!0&&(v=1),g===!0&&(v=2),x===!0&&(v=3);let M=a.attributes.position.count*v,S=1;M>e.maxTextureSize&&(S=Math.ceil(M/e.maxTextureSize),M=e.maxTextureSize);const E=new Float32Array(M*S*4*u),C=new Rh(E,M,S,u);C.type=Tn,C.needsUpdate=!0;const z=v*4;for(let y=0;y<u;y++){const b=p[y],D=m[y],L=_[y],N=M*S*4*y;for(let B=0;B<b.count;B++){const k=B*z;f===!0&&(i.fromBufferAttribute(b,B),E[N+k+0]=i.x,E[N+k+1]=i.y,E[N+k+2]=i.z,E[N+k+3]=0),g===!0&&(i.fromBufferAttribute(D,B),E[N+k+4]=i.x,E[N+k+5]=i.y,E[N+k+6]=i.z,E[N+k+7]=0),x===!0&&(i.fromBufferAttribute(L,B),E[N+k+8]=i.x,E[N+k+9]=i.y,E[N+k+10]=i.z,E[N+k+11]=L.itemSize===4?i.w:1)}}d={count:u,texture:C,size:new Q(M,S)},n.set(a,d),a.addEventListener("dispose",T)}if(o.isInstancedMesh===!0&&o.morphTexture!==null)l.getUniforms().setValue(s,"morphTexture",o.morphTexture,t);else{let f=0;for(let x=0;x<c.length;x++)f+=c[x];const g=a.morphTargetsRelative?1:1-f;l.getUniforms().setValue(s,"morphTargetBaseInfluence",g),l.getUniforms().setValue(s,"morphTargetInfluences",c)}l.getUniforms().setValue(s,"morphTargetsTexture",d.texture,t),l.getUniforms().setValue(s,"morphTargetsTextureSize",d.size)}return{update:r}}function jp(s,e,t,n){let i=new WeakMap;function r(l){const c=n.render.frame,h=l.geometry,u=e.get(l,h);if(i.get(u)!==c&&(e.update(u),i.set(u,c)),l.isInstancedMesh&&(l.hasEventListener("dispose",a)===!1&&l.addEventListener("dispose",a),i.get(l)!==c&&(t.update(l.instanceMatrix,s.ARRAY_BUFFER),l.instanceColor!==null&&t.update(l.instanceColor,s.ARRAY_BUFFER),i.set(l,c))),l.isSkinnedMesh){const d=l.skeleton;i.get(d)!==c&&(d.update(),i.set(d,c))}return u}function o(){i=new WeakMap}function a(l){const c=l.target;c.removeEventListener("dispose",a),t.remove(c.instanceMatrix),c.instanceColor!==null&&t.remove(c.instanceColor)}return{update:r,dispose:o}}class zh extends It{constructor(e,t,n,i,r,o,a,l,c,h=ji){if(h!==ji&&h!==ts)throw new Error("DepthTexture format must be either THREE.DepthFormat or THREE.DepthStencilFormat");n===void 0&&h===ji&&(n=gi),n===void 0&&h===ts&&(n=es),super(null,i,r,o,a,l,h,n,c),this.isDepthTexture=!0,this.image={width:e,height:t},this.magFilter=a!==void 0?a:$t,this.minFilter=l!==void 0?l:$t,this.flipY=!1,this.generateMipmaps=!1,this.compareFunction=null}copy(e){return super.copy(e),this.compareFunction=e.compareFunction,this}toJSON(e){const t=super.toJSON(e);return this.compareFunction!==null&&(t.compareFunction=this.compareFunction),t}}const kh=new It,ec=new zh(1,1),Bh=new Rh,Vh=new Dd,Hh=new Oh,tc=[],nc=[],ic=new Float32Array(16),sc=new Float32Array(9),rc=new Float32Array(4);function as(s,e,t){const n=s[0];if(n<=0||n>0)return s;const i=e*t;let r=tc[i];if(r===void 0&&(r=new Float32Array(i),tc[i]=r),e!==0){n.toArray(r,0);for(let o=1,a=0;o!==e;++o)a+=t,s[o].toArray(r,a)}return r}function Nt(s,e){if(s.length!==e.length)return!1;for(let t=0,n=s.length;t<n;t++)if(s[t]!==e[t])return!1;return!0}function Ut(s,e){for(let t=0,n=e.length;t<n;t++)s[t]=e[t]}function qr(s,e){let t=nc[e];t===void 0&&(t=new Int32Array(e),nc[e]=t);for(let n=0;n!==e;++n)t[n]=s.allocateTextureUnit();return t}function Kp(s,e){const t=this.cache;t[0]!==e&&(s.uniform1f(this.addr,e),t[0]=e)}function Zp(s,e){const t=this.cache;if(e.x!==void 0)(t[0]!==e.x||t[1]!==e.y)&&(s.uniform2f(this.addr,e.x,e.y),t[0]=e.x,t[1]=e.y);else{if(Nt(t,e))return;s.uniform2fv(this.addr,e),Ut(t,e)}}function Jp(s,e){const t=this.cache;if(e.x!==void 0)(t[0]!==e.x||t[1]!==e.y||t[2]!==e.z)&&(s.uniform3f(this.addr,e.x,e.y,e.z),t[0]=e.x,t[1]=e.y,t[2]=e.z);else if(e.r!==void 0)(t[0]!==e.r||t[1]!==e.g||t[2]!==e.b)&&(s.uniform3f(this.addr,e.r,e.g,e.b),t[0]=e.r,t[1]=e.g,t[2]=e.b);else{if(Nt(t,e))return;s.uniform3fv(this.addr,e),Ut(t,e)}}function $p(s,e){const t=this.cache;if(e.x!==void 0)(t[0]!==e.x||t[1]!==e.y||t[2]!==e.z||t[3]!==e.w)&&(s.uniform4f(this.addr,e.x,e.y,e.z,e.w),t[0]=e.x,t[1]=e.y,t[2]=e.z,t[3]=e.w);else{if(Nt(t,e))return;s.uniform4fv(this.addr,e),Ut(t,e)}}function Qp(s,e){const t=this.cache,n=e.elements;if(n===void 0){if(Nt(t,e))return;s.uniformMatrix2fv(this.addr,!1,e),Ut(t,e)}else{if(Nt(t,n))return;rc.set(n),s.uniformMatrix2fv(this.addr,!1,rc),Ut(t,n)}}function em(s,e){const t=this.cache,n=e.elements;if(n===void 0){if(Nt(t,e))return;s.uniformMatrix3fv(this.addr,!1,e),Ut(t,e)}else{if(Nt(t,n))return;sc.set(n),s.uniformMatrix3fv(this.addr,!1,sc),Ut(t,n)}}function tm(s,e){const t=this.cache,n=e.elements;if(n===void 0){if(Nt(t,e))return;s.uniformMatrix4fv(this.addr,!1,e),Ut(t,e)}else{if(Nt(t,n))return;ic.set(n),s.uniformMatrix4fv(this.addr,!1,ic),Ut(t,n)}}function nm(s,e){const t=this.cache;t[0]!==e&&(s.uniform1i(this.addr,e),t[0]=e)}function im(s,e){const t=this.cache;if(e.x!==void 0)(t[0]!==e.x||t[1]!==e.y)&&(s.uniform2i(this.addr,e.x,e.y),t[0]=e.x,t[1]=e.y);else{if(Nt(t,e))return;s.uniform2iv(this.addr,e),Ut(t,e)}}function sm(s,e){const t=this.cache;if(e.x!==void 0)(t[0]!==e.x||t[1]!==e.y||t[2]!==e.z)&&(s.uniform3i(this.addr,e.x,e.y,e.z),t[0]=e.x,t[1]=e.y,t[2]=e.z);else{if(Nt(t,e))return;s.uniform3iv(this.addr,e),Ut(t,e)}}function rm(s,e){const t=this.cache;if(e.x!==void 0)(t[0]!==e.x||t[1]!==e.y||t[2]!==e.z||t[3]!==e.w)&&(s.uniform4i(this.addr,e.x,e.y,e.z,e.w),t[0]=e.x,t[1]=e.y,t[2]=e.z,t[3]=e.w);else{if(Nt(t,e))return;s.uniform4iv(this.addr,e),Ut(t,e)}}function om(s,e){const t=this.cache;t[0]!==e&&(s.uniform1ui(this.addr,e),t[0]=e)}function am(s,e){const t=this.cache;if(e.x!==void 0)(t[0]!==e.x||t[1]!==e.y)&&(s.uniform2ui(this.addr,e.x,e.y),t[0]=e.x,t[1]=e.y);else{if(Nt(t,e))return;s.uniform2uiv(this.addr,e),Ut(t,e)}}function lm(s,e){const t=this.cache;if(e.x!==void 0)(t[0]!==e.x||t[1]!==e.y||t[2]!==e.z)&&(s.uniform3ui(this.addr,e.x,e.y,e.z),t[0]=e.x,t[1]=e.y,t[2]=e.z);else{if(Nt(t,e))return;s.uniform3uiv(this.addr,e),Ut(t,e)}}function cm(s,e){const t=this.cache;if(e.x!==void 0)(t[0]!==e.x||t[1]!==e.y||t[2]!==e.z||t[3]!==e.w)&&(s.uniform4ui(this.addr,e.x,e.y,e.z,e.w),t[0]=e.x,t[1]=e.y,t[2]=e.z,t[3]=e.w);else{if(Nt(t,e))return;s.uniform4uiv(this.addr,e),Ut(t,e)}}function hm(s,e,t){const n=this.cache,i=t.allocateTextureUnit();n[0]!==i&&(s.uniform1i(this.addr,i),n[0]=i);let r;this.type===s.SAMPLER_2D_SHADOW?(ec.compareFunction=Ah,r=ec):r=kh,t.setTexture2D(e||r,i)}function um(s,e,t){const n=this.cache,i=t.allocateTextureUnit();n[0]!==i&&(s.uniform1i(this.addr,i),n[0]=i),t.setTexture3D(e||Vh,i)}function dm(s,e,t){const n=this.cache,i=t.allocateTextureUnit();n[0]!==i&&(s.uniform1i(this.addr,i),n[0]=i),t.setTextureCube(e||Hh,i)}function fm(s,e,t){const n=this.cache,i=t.allocateTextureUnit();n[0]!==i&&(s.uniform1i(this.addr,i),n[0]=i),t.setTexture2DArray(e||Bh,i)}function pm(s){switch(s){case 5126:return Kp;case 35664:return Zp;case 35665:return Jp;case 35666:return $p;case 35674:return Qp;case 35675:return em;case 35676:return tm;case 5124:case 35670:return nm;case 35667:case 35671:return im;case 35668:case 35672:return sm;case 35669:case 35673:return rm;case 5125:return om;case 36294:return am;case 36295:return lm;case 36296:return cm;case 35678:case 36198:case 36298:case 36306:case 35682:return hm;case 35679:case 36299:case 36307:return um;case 35680:case 36300:case 36308:case 36293:return dm;case 36289:case 36303:case 36311:case 36292:return fm}}function mm(s,e){s.uniform1fv(this.addr,e)}function gm(s,e){const t=as(e,this.size,2);s.uniform2fv(this.addr,t)}function vm(s,e){const t=as(e,this.size,3);s.uniform3fv(this.addr,t)}function xm(s,e){const t=as(e,this.size,4);s.uniform4fv(this.addr,t)}function _m(s,e){const t=as(e,this.size,4);s.uniformMatrix2fv(this.addr,!1,t)}function ym(s,e){const t=as(e,this.size,9);s.uniformMatrix3fv(this.addr,!1,t)}function Mm(s,e){const t=as(e,this.size,16);s.uniformMatrix4fv(this.addr,!1,t)}function bm(s,e){s.uniform1iv(this.addr,e)}function wm(s,e){s.uniform2iv(this.addr,e)}function Sm(s,e){s.uniform3iv(this.addr,e)}function Tm(s,e){s.uniform4iv(this.addr,e)}function Em(s,e){s.uniform1uiv(this.addr,e)}function Am(s,e){s.uniform2uiv(this.addr,e)}function Cm(s,e){s.uniform3uiv(this.addr,e)}function Pm(s,e){s.uniform4uiv(this.addr,e)}function Rm(s,e,t){const n=this.cache,i=e.length,r=qr(t,i);Nt(n,r)||(s.uniform1iv(this.addr,r),Ut(n,r));for(let o=0;o!==i;++o)t.setTexture2D(e[o]||kh,r[o])}function Dm(s,e,t){const n=this.cache,i=e.length,r=qr(t,i);Nt(n,r)||(s.uniform1iv(this.addr,r),Ut(n,r));for(let o=0;o!==i;++o)t.setTexture3D(e[o]||Vh,r[o])}function Im(s,e,t){const n=this.cache,i=e.length,r=qr(t,i);Nt(n,r)||(s.uniform1iv(this.addr,r),Ut(n,r));for(let o=0;o!==i;++o)t.setTextureCube(e[o]||Hh,r[o])}function Lm(s,e,t){const n=this.cache,i=e.length,r=qr(t,i);Nt(n,r)||(s.uniform1iv(this.addr,r),Ut(n,r));for(let o=0;o!==i;++o)t.setTexture2DArray(e[o]||Bh,r[o])}function Nm(s){switch(s){case 5126:return mm;case 35664:return gm;case 35665:return vm;case 35666:return xm;case 35674:return _m;case 35675:return ym;case 35676:return Mm;case 5124:case 35670:return bm;case 35667:case 35671:return wm;case 35668:case 35672:return Sm;case 35669:case 35673:return Tm;case 5125:return Em;case 36294:return Am;case 36295:return Cm;case 36296:return Pm;case 35678:case 36198:case 36298:case 36306:case 35682:return Rm;case 35679:case 36299:case 36307:return Dm;case 35680:case 36300:case 36308:case 36293:return Im;case 36289:case 36303:case 36311:case 36292:return Lm}}class Um{constructor(e,t,n){this.id=e,this.addr=n,this.cache=[],this.type=t.type,this.setValue=pm(t.type)}}class Om{constructor(e,t,n){this.id=e,this.addr=n,this.cache=[],this.type=t.type,this.size=t.size,this.setValue=Nm(t.type)}}class Fm{constructor(e){this.id=e,this.seq=[],this.map={}}setValue(e,t,n){const i=this.seq;for(let r=0,o=i.length;r!==o;++r){const a=i[r];a.setValue(e,t[a.id],n)}}}const Io=/(\w+)(\])?(\[|\.)?/g;function oc(s,e){s.seq.push(e),s.map[e.id]=e}function zm(s,e,t){const n=s.name,i=n.length;for(Io.lastIndex=0;;){const r=Io.exec(n),o=Io.lastIndex;let a=r[1];const l=r[2]==="]",c=r[3];if(l&&(a=a|0),c===void 0||c==="["&&o+2===i){oc(t,c===void 0?new Um(a,s,e):new Om(a,s,e));break}else{let u=t.map[a];u===void 0&&(u=new Fm(a),oc(t,u)),t=u}}}class Pr{constructor(e,t){this.seq=[],this.map={};const n=e.getProgramParameter(t,e.ACTIVE_UNIFORMS);for(let i=0;i<n;++i){const r=e.getActiveUniform(t,i),o=e.getUniformLocation(t,r.name);zm(r,o,this)}}setValue(e,t,n,i){const r=this.map[t];r!==void 0&&r.setValue(e,n,i)}setOptional(e,t,n){const i=t[n];i!==void 0&&this.setValue(e,n,i)}static upload(e,t,n,i){for(let r=0,o=t.length;r!==o;++r){const a=t[r],l=n[a.id];l.needsUpdate!==!1&&a.setValue(e,l.value,i)}}static seqWithValue(e,t){const n=[];for(let i=0,r=e.length;i!==r;++i){const o=e[i];o.id in t&&n.push(o)}return n}}function ac(s,e,t){const n=s.createShader(e);return s.shaderSource(n,t),s.compileShader(n),n}const km=37297;let Bm=0;function Vm(s,e){const t=s.split(`
`),n=[],i=Math.max(e-6,0),r=Math.min(e+6,t.length);for(let o=i;o<r;o++){const a=o+1;n.push(`${a===e?">":" "} ${a}: ${t[o]}`)}return n.join(`
`)}function Hm(s){const e=nt.getPrimaries(nt.workingColorSpace),t=nt.getPrimaries(s);let n;switch(e===t?n="":e===Nr&&t===Lr?n="LinearDisplayP3ToLinearSRGB":e===Lr&&t===Nr&&(n="LinearSRGBToLinearDisplayP3"),s){case Hn:case Yr:return[n,"LinearTransferOETF"];case Ft:case Ja:return[n,"sRGBTransferOETF"];default:return console.warn("THREE.WebGLProgram: Unsupported color space:",s),[n,"LinearTransferOETF"]}}function lc(s,e,t){const n=s.getShaderParameter(e,s.COMPILE_STATUS),i=s.getShaderInfoLog(e).trim();if(n&&i==="")return"";const r=/ERROR: 0:(\d+)/.exec(i);if(r){const o=parseInt(r[1]);return t.toUpperCase()+`

`+i+`

`+Vm(s.getShaderSource(e),o)}else return i}function Gm(s,e){const t=Hm(e);return`vec4 ${s}( vec4 value ) { return ${t[0]}( ${t[1]}( value ) ); }`}function Wm(s,e){let t;switch(e){case uh:t="Linear";break;case dh:t="Reinhard";break;case fh:t="Cineon";break;case Wr:t="ACESFilmic";break;case ph:t="AgX";break;case mh:t="Neutral";break;case qu:t="Custom";break;default:console.warn("THREE.WebGLProgram: Unsupported toneMapping:",e),t="Linear"}return"vec3 "+s+"( vec3 color ) { return "+t+"ToneMapping( color ); }"}const cr=new w;function Xm(){nt.getLuminanceCoefficients(cr);const s=cr.x.toFixed(4),e=cr.y.toFixed(4),t=cr.z.toFixed(4);return["float luminance( const in vec3 rgb ) {",`	const vec3 weights = vec3( ${s}, ${e}, ${t} );`,"	return dot( weights, rgb );","}"].join(`
`)}function Ym(s){return[s.extensionClipCullDistance?"#extension GL_ANGLE_clip_cull_distance : require":"",s.extensionMultiDraw?"#extension GL_ANGLE_multi_draw : require":""].filter(bs).join(`
`)}function qm(s){const e=[];for(const t in s){const n=s[t];n!==!1&&e.push("#define "+t+" "+n)}return e.join(`
`)}function jm(s,e){const t={},n=s.getProgramParameter(e,s.ACTIVE_ATTRIBUTES);for(let i=0;i<n;i++){const r=s.getActiveAttrib(e,i),o=r.name;let a=1;r.type===s.FLOAT_MAT2&&(a=2),r.type===s.FLOAT_MAT3&&(a=3),r.type===s.FLOAT_MAT4&&(a=4),t[o]={type:r.type,location:s.getAttribLocation(e,o),locationSize:a}}return t}function bs(s){return s!==""}function cc(s,e){const t=e.numSpotLightShadows+e.numSpotLightMaps-e.numSpotLightShadowsWithMaps;return s.replace(/NUM_DIR_LIGHTS/g,e.numDirLights).replace(/NUM_SPOT_LIGHTS/g,e.numSpotLights).replace(/NUM_SPOT_LIGHT_MAPS/g,e.numSpotLightMaps).replace(/NUM_SPOT_LIGHT_COORDS/g,t).replace(/NUM_RECT_AREA_LIGHTS/g,e.numRectAreaLights).replace(/NUM_POINT_LIGHTS/g,e.numPointLights).replace(/NUM_HEMI_LIGHTS/g,e.numHemiLights).replace(/NUM_DIR_LIGHT_SHADOWS/g,e.numDirLightShadows).replace(/NUM_SPOT_LIGHT_SHADOWS_WITH_MAPS/g,e.numSpotLightShadowsWithMaps).replace(/NUM_SPOT_LIGHT_SHADOWS/g,e.numSpotLightShadows).replace(/NUM_POINT_LIGHT_SHADOWS/g,e.numPointLightShadows)}function hc(s,e){return s.replace(/NUM_CLIPPING_PLANES/g,e.numClippingPlanes).replace(/UNION_CLIPPING_PLANES/g,e.numClippingPlanes-e.numClipIntersection)}const Km=/^[ \t]*#include +<([\w\d./]+)>/gm;function Da(s){return s.replace(Km,Jm)}const Zm=new Map;function Jm(s,e){let t=Xe[e];if(t===void 0){const n=Zm.get(e);if(n!==void 0)t=Xe[n],console.warn('THREE.WebGLRenderer: Shader chunk "%s" has been deprecated. Use "%s" instead.',e,n);else throw new Error("Can not resolve #include <"+e+">")}return Da(t)}const $m=/#pragma unroll_loop_start\s+for\s*\(\s*int\s+i\s*=\s*(\d+)\s*;\s*i\s*<\s*(\d+)\s*;\s*i\s*\+\+\s*\)\s*{([\s\S]+?)}\s+#pragma unroll_loop_end/g;function uc(s){return s.replace($m,Qm)}function Qm(s,e,t,n){let i="";for(let r=parseInt(e);r<parseInt(t);r++)i+=n.replace(/\[\s*i\s*\]/g,"[ "+r+" ]").replace(/UNROLLED_LOOP_INDEX/g,r);return i}function dc(s){let e=`precision ${s.precision} float;
	precision ${s.precision} int;
	precision ${s.precision} sampler2D;
	precision ${s.precision} samplerCube;
	precision ${s.precision} sampler3D;
	precision ${s.precision} sampler2DArray;
	precision ${s.precision} sampler2DShadow;
	precision ${s.precision} samplerCubeShadow;
	precision ${s.precision} sampler2DArrayShadow;
	precision ${s.precision} isampler2D;
	precision ${s.precision} isampler3D;
	precision ${s.precision} isamplerCube;
	precision ${s.precision} isampler2DArray;
	precision ${s.precision} usampler2D;
	precision ${s.precision} usampler3D;
	precision ${s.precision} usamplerCube;
	precision ${s.precision} usampler2DArray;
	`;return s.precision==="highp"?e+=`
#define HIGH_PRECISION`:s.precision==="mediump"?e+=`
#define MEDIUM_PRECISION`:s.precision==="lowp"&&(e+=`
#define LOW_PRECISION`),e}function eg(s){let e="SHADOWMAP_TYPE_BASIC";return s.shadowMapType===lh?e="SHADOWMAP_TYPE_PCF":s.shadowMapType===ch?e="SHADOWMAP_TYPE_PCF_SOFT":s.shadowMapType===Un&&(e="SHADOWMAP_TYPE_VSM"),e}function tg(s){let e="ENVMAP_TYPE_CUBE";if(s.envMap)switch(s.envMapMode){case $i:case Qi:e="ENVMAP_TYPE_CUBE";break;case Xr:e="ENVMAP_TYPE_CUBE_UV";break}return e}function ng(s){let e="ENVMAP_MODE_REFLECTION";if(s.envMap)switch(s.envMapMode){case Qi:e="ENVMAP_MODE_REFRACTION";break}return e}function ig(s){let e="ENVMAP_BLENDING_NONE";if(s.envMap)switch(s.combine){case hh:e="ENVMAP_BLENDING_MULTIPLY";break;case Xu:e="ENVMAP_BLENDING_MIX";break;case Yu:e="ENVMAP_BLENDING_ADD";break}return e}function sg(s){const e=s.envMapCubeUVHeight;if(e===null)return null;const t=Math.log2(e)-2,n=1/e;return{texelWidth:1/(3*Math.max(Math.pow(2,t),7*16)),texelHeight:n,maxMip:t}}function rg(s,e,t,n){const i=s.getContext(),r=t.defines;let o=t.vertexShader,a=t.fragmentShader;const l=eg(t),c=tg(t),h=ng(t),u=ig(t),d=sg(t),f=Ym(t),g=qm(r),x=i.createProgram();let p,m,_=t.glslVersion?"#version "+t.glslVersion+`
`:"";t.isRawShaderMaterial?(p=["#define SHADER_TYPE "+t.shaderType,"#define SHADER_NAME "+t.shaderName,g].filter(bs).join(`
`),p.length>0&&(p+=`
`),m=["#define SHADER_TYPE "+t.shaderType,"#define SHADER_NAME "+t.shaderName,g].filter(bs).join(`
`),m.length>0&&(m+=`
`)):(p=[dc(t),"#define SHADER_TYPE "+t.shaderType,"#define SHADER_NAME "+t.shaderName,g,t.extensionClipCullDistance?"#define USE_CLIP_DISTANCE":"",t.batching?"#define USE_BATCHING":"",t.batchingColor?"#define USE_BATCHING_COLOR":"",t.instancing?"#define USE_INSTANCING":"",t.instancingColor?"#define USE_INSTANCING_COLOR":"",t.instancingMorph?"#define USE_INSTANCING_MORPH":"",t.useFog&&t.fog?"#define USE_FOG":"",t.useFog&&t.fogExp2?"#define FOG_EXP2":"",t.map?"#define USE_MAP":"",t.envMap?"#define USE_ENVMAP":"",t.envMap?"#define "+h:"",t.lightMap?"#define USE_LIGHTMAP":"",t.aoMap?"#define USE_AOMAP":"",t.bumpMap?"#define USE_BUMPMAP":"",t.normalMap?"#define USE_NORMALMAP":"",t.normalMapObjectSpace?"#define USE_NORMALMAP_OBJECTSPACE":"",t.normalMapTangentSpace?"#define USE_NORMALMAP_TANGENTSPACE":"",t.displacementMap?"#define USE_DISPLACEMENTMAP":"",t.emissiveMap?"#define USE_EMISSIVEMAP":"",t.anisotropy?"#define USE_ANISOTROPY":"",t.anisotropyMap?"#define USE_ANISOTROPYMAP":"",t.clearcoatMap?"#define USE_CLEARCOATMAP":"",t.clearcoatRoughnessMap?"#define USE_CLEARCOAT_ROUGHNESSMAP":"",t.clearcoatNormalMap?"#define USE_CLEARCOAT_NORMALMAP":"",t.iridescenceMap?"#define USE_IRIDESCENCEMAP":"",t.iridescenceThicknessMap?"#define USE_IRIDESCENCE_THICKNESSMAP":"",t.specularMap?"#define USE_SPECULARMAP":"",t.specularColorMap?"#define USE_SPECULAR_COLORMAP":"",t.specularIntensityMap?"#define USE_SPECULAR_INTENSITYMAP":"",t.roughnessMap?"#define USE_ROUGHNESSMAP":"",t.metalnessMap?"#define USE_METALNESSMAP":"",t.alphaMap?"#define USE_ALPHAMAP":"",t.alphaHash?"#define USE_ALPHAHASH":"",t.transmission?"#define USE_TRANSMISSION":"",t.transmissionMap?"#define USE_TRANSMISSIONMAP":"",t.thicknessMap?"#define USE_THICKNESSMAP":"",t.sheenColorMap?"#define USE_SHEEN_COLORMAP":"",t.sheenRoughnessMap?"#define USE_SHEEN_ROUGHNESSMAP":"",t.mapUv?"#define MAP_UV "+t.mapUv:"",t.alphaMapUv?"#define ALPHAMAP_UV "+t.alphaMapUv:"",t.lightMapUv?"#define LIGHTMAP_UV "+t.lightMapUv:"",t.aoMapUv?"#define AOMAP_UV "+t.aoMapUv:"",t.emissiveMapUv?"#define EMISSIVEMAP_UV "+t.emissiveMapUv:"",t.bumpMapUv?"#define BUMPMAP_UV "+t.bumpMapUv:"",t.normalMapUv?"#define NORMALMAP_UV "+t.normalMapUv:"",t.displacementMapUv?"#define DISPLACEMENTMAP_UV "+t.displacementMapUv:"",t.metalnessMapUv?"#define METALNESSMAP_UV "+t.metalnessMapUv:"",t.roughnessMapUv?"#define ROUGHNESSMAP_UV "+t.roughnessMapUv:"",t.anisotropyMapUv?"#define ANISOTROPYMAP_UV "+t.anisotropyMapUv:"",t.clearcoatMapUv?"#define CLEARCOATMAP_UV "+t.clearcoatMapUv:"",t.clearcoatNormalMapUv?"#define CLEARCOAT_NORMALMAP_UV "+t.clearcoatNormalMapUv:"",t.clearcoatRoughnessMapUv?"#define CLEARCOAT_ROUGHNESSMAP_UV "+t.clearcoatRoughnessMapUv:"",t.iridescenceMapUv?"#define IRIDESCENCEMAP_UV "+t.iridescenceMapUv:"",t.iridescenceThicknessMapUv?"#define IRIDESCENCE_THICKNESSMAP_UV "+t.iridescenceThicknessMapUv:"",t.sheenColorMapUv?"#define SHEEN_COLORMAP_UV "+t.sheenColorMapUv:"",t.sheenRoughnessMapUv?"#define SHEEN_ROUGHNESSMAP_UV "+t.sheenRoughnessMapUv:"",t.specularMapUv?"#define SPECULARMAP_UV "+t.specularMapUv:"",t.specularColorMapUv?"#define SPECULAR_COLORMAP_UV "+t.specularColorMapUv:"",t.specularIntensityMapUv?"#define SPECULAR_INTENSITYMAP_UV "+t.specularIntensityMapUv:"",t.transmissionMapUv?"#define TRANSMISSIONMAP_UV "+t.transmissionMapUv:"",t.thicknessMapUv?"#define THICKNESSMAP_UV "+t.thicknessMapUv:"",t.vertexTangents&&t.flatShading===!1?"#define USE_TANGENT":"",t.vertexColors?"#define USE_COLOR":"",t.vertexAlphas?"#define USE_COLOR_ALPHA":"",t.vertexUv1s?"#define USE_UV1":"",t.vertexUv2s?"#define USE_UV2":"",t.vertexUv3s?"#define USE_UV3":"",t.pointsUvs?"#define USE_POINTS_UV":"",t.flatShading?"#define FLAT_SHADED":"",t.skinning?"#define USE_SKINNING":"",t.morphTargets?"#define USE_MORPHTARGETS":"",t.morphNormals&&t.flatShading===!1?"#define USE_MORPHNORMALS":"",t.morphColors?"#define USE_MORPHCOLORS":"",t.morphTargetsCount>0?"#define MORPHTARGETS_TEXTURE_STRIDE "+t.morphTextureStride:"",t.morphTargetsCount>0?"#define MORPHTARGETS_COUNT "+t.morphTargetsCount:"",t.doubleSided?"#define DOUBLE_SIDED":"",t.flipSided?"#define FLIP_SIDED":"",t.shadowMapEnabled?"#define USE_SHADOWMAP":"",t.shadowMapEnabled?"#define "+l:"",t.sizeAttenuation?"#define USE_SIZEATTENUATION":"",t.numLightProbes>0?"#define USE_LIGHT_PROBES":"",t.logarithmicDepthBuffer?"#define USE_LOGDEPTHBUF":"",t.reverseDepthBuffer?"#define USE_REVERSEDEPTHBUF":"","uniform mat4 modelMatrix;","uniform mat4 modelViewMatrix;","uniform mat4 projectionMatrix;","uniform mat4 viewMatrix;","uniform mat3 normalMatrix;","uniform vec3 cameraPosition;","uniform bool isOrthographic;","#ifdef USE_INSTANCING","	attribute mat4 instanceMatrix;","#endif","#ifdef USE_INSTANCING_COLOR","	attribute vec3 instanceColor;","#endif","#ifdef USE_INSTANCING_MORPH","	uniform sampler2D morphTexture;","#endif","attribute vec3 position;","attribute vec3 normal;","attribute vec2 uv;","#ifdef USE_UV1","	attribute vec2 uv1;","#endif","#ifdef USE_UV2","	attribute vec2 uv2;","#endif","#ifdef USE_UV3","	attribute vec2 uv3;","#endif","#ifdef USE_TANGENT","	attribute vec4 tangent;","#endif","#if defined( USE_COLOR_ALPHA )","	attribute vec4 color;","#elif defined( USE_COLOR )","	attribute vec3 color;","#endif","#ifdef USE_SKINNING","	attribute vec4 skinIndex;","	attribute vec4 skinWeight;","#endif",`
`].filter(bs).join(`
`),m=[dc(t),"#define SHADER_TYPE "+t.shaderType,"#define SHADER_NAME "+t.shaderName,g,t.useFog&&t.fog?"#define USE_FOG":"",t.useFog&&t.fogExp2?"#define FOG_EXP2":"",t.alphaToCoverage?"#define ALPHA_TO_COVERAGE":"",t.map?"#define USE_MAP":"",t.matcap?"#define USE_MATCAP":"",t.envMap?"#define USE_ENVMAP":"",t.envMap?"#define "+c:"",t.envMap?"#define "+h:"",t.envMap?"#define "+u:"",d?"#define CUBEUV_TEXEL_WIDTH "+d.texelWidth:"",d?"#define CUBEUV_TEXEL_HEIGHT "+d.texelHeight:"",d?"#define CUBEUV_MAX_MIP "+d.maxMip+".0":"",t.lightMap?"#define USE_LIGHTMAP":"",t.aoMap?"#define USE_AOMAP":"",t.bumpMap?"#define USE_BUMPMAP":"",t.normalMap?"#define USE_NORMALMAP":"",t.normalMapObjectSpace?"#define USE_NORMALMAP_OBJECTSPACE":"",t.normalMapTangentSpace?"#define USE_NORMALMAP_TANGENTSPACE":"",t.emissiveMap?"#define USE_EMISSIVEMAP":"",t.anisotropy?"#define USE_ANISOTROPY":"",t.anisotropyMap?"#define USE_ANISOTROPYMAP":"",t.clearcoat?"#define USE_CLEARCOAT":"",t.clearcoatMap?"#define USE_CLEARCOATMAP":"",t.clearcoatRoughnessMap?"#define USE_CLEARCOAT_ROUGHNESSMAP":"",t.clearcoatNormalMap?"#define USE_CLEARCOAT_NORMALMAP":"",t.dispersion?"#define USE_DISPERSION":"",t.iridescence?"#define USE_IRIDESCENCE":"",t.iridescenceMap?"#define USE_IRIDESCENCEMAP":"",t.iridescenceThicknessMap?"#define USE_IRIDESCENCE_THICKNESSMAP":"",t.specularMap?"#define USE_SPECULARMAP":"",t.specularColorMap?"#define USE_SPECULAR_COLORMAP":"",t.specularIntensityMap?"#define USE_SPECULAR_INTENSITYMAP":"",t.roughnessMap?"#define USE_ROUGHNESSMAP":"",t.metalnessMap?"#define USE_METALNESSMAP":"",t.alphaMap?"#define USE_ALPHAMAP":"",t.alphaTest?"#define USE_ALPHATEST":"",t.alphaHash?"#define USE_ALPHAHASH":"",t.sheen?"#define USE_SHEEN":"",t.sheenColorMap?"#define USE_SHEEN_COLORMAP":"",t.sheenRoughnessMap?"#define USE_SHEEN_ROUGHNESSMAP":"",t.transmission?"#define USE_TRANSMISSION":"",t.transmissionMap?"#define USE_TRANSMISSIONMAP":"",t.thicknessMap?"#define USE_THICKNESSMAP":"",t.vertexTangents&&t.flatShading===!1?"#define USE_TANGENT":"",t.vertexColors||t.instancingColor||t.batchingColor?"#define USE_COLOR":"",t.vertexAlphas?"#define USE_COLOR_ALPHA":"",t.vertexUv1s?"#define USE_UV1":"",t.vertexUv2s?"#define USE_UV2":"",t.vertexUv3s?"#define USE_UV3":"",t.pointsUvs?"#define USE_POINTS_UV":"",t.gradientMap?"#define USE_GRADIENTMAP":"",t.flatShading?"#define FLAT_SHADED":"",t.doubleSided?"#define DOUBLE_SIDED":"",t.flipSided?"#define FLIP_SIDED":"",t.shadowMapEnabled?"#define USE_SHADOWMAP":"",t.shadowMapEnabled?"#define "+l:"",t.premultipliedAlpha?"#define PREMULTIPLIED_ALPHA":"",t.numLightProbes>0?"#define USE_LIGHT_PROBES":"",t.decodeVideoTexture?"#define DECODE_VIDEO_TEXTURE":"",t.logarithmicDepthBuffer?"#define USE_LOGDEPTHBUF":"",t.reverseDepthBuffer?"#define USE_REVERSEDEPTHBUF":"","uniform mat4 viewMatrix;","uniform vec3 cameraPosition;","uniform bool isOrthographic;",t.toneMapping!==ei?"#define TONE_MAPPING":"",t.toneMapping!==ei?Xe.tonemapping_pars_fragment:"",t.toneMapping!==ei?Wm("toneMapping",t.toneMapping):"",t.dithering?"#define DITHERING":"",t.opaque?"#define OPAQUE":"",Xe.colorspace_pars_fragment,Gm("linearToOutputTexel",t.outputColorSpace),Xm(),t.useDepthPacking?"#define DEPTH_PACKING "+t.depthPacking:"",`
`].filter(bs).join(`
`)),o=Da(o),o=cc(o,t),o=hc(o,t),a=Da(a),a=cc(a,t),a=hc(a,t),o=uc(o),a=uc(a),t.isRawShaderMaterial!==!0&&(_=`#version 300 es
`,p=[f,"#define attribute in","#define varying out","#define texture2D texture"].join(`
`)+`
`+p,m=["#define varying in",t.glslVersion===Pl?"":"layout(location = 0) out highp vec4 pc_fragColor;",t.glslVersion===Pl?"":"#define gl_FragColor pc_fragColor","#define gl_FragDepthEXT gl_FragDepth","#define texture2D texture","#define textureCube texture","#define texture2DProj textureProj","#define texture2DLodEXT textureLod","#define texture2DProjLodEXT textureProjLod","#define textureCubeLodEXT textureLod","#define texture2DGradEXT textureGrad","#define texture2DProjGradEXT textureProjGrad","#define textureCubeGradEXT textureGrad"].join(`
`)+`
`+m);const v=_+p+o,M=_+m+a,S=ac(i,i.VERTEX_SHADER,v),E=ac(i,i.FRAGMENT_SHADER,M);i.attachShader(x,S),i.attachShader(x,E),t.index0AttributeName!==void 0?i.bindAttribLocation(x,0,t.index0AttributeName):t.morphTargets===!0&&i.bindAttribLocation(x,0,"position"),i.linkProgram(x);function C(b){if(s.debug.checkShaderErrors){const D=i.getProgramInfoLog(x).trim(),L=i.getShaderInfoLog(S).trim(),N=i.getShaderInfoLog(E).trim();let B=!0,k=!0;if(i.getProgramParameter(x,i.LINK_STATUS)===!1)if(B=!1,typeof s.debug.onShaderError=="function")s.debug.onShaderError(i,x,S,E);else{const q=lc(i,S,"vertex"),U=lc(i,E,"fragment");console.error("THREE.WebGLProgram: Shader Error "+i.getError()+" - VALIDATE_STATUS "+i.getProgramParameter(x,i.VALIDATE_STATUS)+`

Material Name: `+b.name+`
Material Type: `+b.type+`

Program Info Log: `+D+`
`+q+`
`+U)}else D!==""?console.warn("THREE.WebGLProgram: Program Info Log:",D):(L===""||N==="")&&(k=!1);k&&(b.diagnostics={runnable:B,programLog:D,vertexShader:{log:L,prefix:p},fragmentShader:{log:N,prefix:m}})}i.deleteShader(S),i.deleteShader(E),z=new Pr(i,x),T=jm(i,x)}let z;this.getUniforms=function(){return z===void 0&&C(this),z};let T;this.getAttributes=function(){return T===void 0&&C(this),T};let y=t.rendererExtensionParallelShaderCompile===!1;return this.isReady=function(){return y===!1&&(y=i.getProgramParameter(x,km)),y},this.destroy=function(){n.releaseStatesOfProgram(this),i.deleteProgram(x),this.program=void 0},this.type=t.shaderType,this.name=t.shaderName,this.id=Bm++,this.cacheKey=e,this.usedTimes=1,this.program=x,this.vertexShader=S,this.fragmentShader=E,this}let og=0;class ag{constructor(){this.shaderCache=new Map,this.materialCache=new Map}update(e){const t=e.vertexShader,n=e.fragmentShader,i=this._getShaderStage(t),r=this._getShaderStage(n),o=this._getShaderCacheForMaterial(e);return o.has(i)===!1&&(o.add(i),i.usedTimes++),o.has(r)===!1&&(o.add(r),r.usedTimes++),this}remove(e){const t=this.materialCache.get(e);for(const n of t)n.usedTimes--,n.usedTimes===0&&this.shaderCache.delete(n.code);return this.materialCache.delete(e),this}getVertexShaderID(e){return this._getShaderStage(e.vertexShader).id}getFragmentShaderID(e){return this._getShaderStage(e.fragmentShader).id}dispose(){this.shaderCache.clear(),this.materialCache.clear()}_getShaderCacheForMaterial(e){const t=this.materialCache;let n=t.get(e);return n===void 0&&(n=new Set,t.set(e,n)),n}_getShaderStage(e){const t=this.shaderCache;let n=t.get(e);return n===void 0&&(n=new lg(e),t.set(e,n)),n}}class lg{constructor(e){this.id=og++,this.code=e,this.usedTimes=0}}function cg(s,e,t,n,i,r,o){const a=new Qa,l=new ag,c=new Set,h=[],u=i.logarithmicDepthBuffer,d=i.reverseDepthBuffer,f=i.vertexTextures;let g=i.precision;const x={MeshDepthMaterial:"depth",MeshDistanceMaterial:"distanceRGBA",MeshNormalMaterial:"normal",MeshBasicMaterial:"basic",MeshLambertMaterial:"lambert",MeshPhongMaterial:"phong",MeshToonMaterial:"toon",MeshStandardMaterial:"physical",MeshPhysicalMaterial:"physical",MeshMatcapMaterial:"matcap",LineBasicMaterial:"basic",LineDashedMaterial:"dashed",PointsMaterial:"points",ShadowMaterial:"shadow",SpriteMaterial:"sprite"};function p(y){return c.add(y),y===0?"uv":`uv${y}`}function m(y,b,D,L,N){const B=L.fog,k=N.geometry,q=y.isMeshStandardMaterial?L.environment:null,U=(y.isMeshStandardMaterial?t:e).get(y.envMap||q),V=U&&U.mapping===Xr?U.image.height:null,P=x[y.type];y.precision!==null&&(g=i.getMaxPrecision(y.precision),g!==y.precision&&console.warn("THREE.WebGLProgram.getParameters:",y.precision,"not supported, using",g,"instead."));const O=k.morphAttributes.position||k.morphAttributes.normal||k.morphAttributes.color,H=O!==void 0?O.length:0;let Z=0;k.morphAttributes.position!==void 0&&(Z=1),k.morphAttributes.normal!==void 0&&(Z=2),k.morphAttributes.color!==void 0&&(Z=3);let W,$,le,he;if(P){const Kt=Sn[P];W=Kt.vertexShader,$=Kt.fragmentShader}else W=y.vertexShader,$=y.fragmentShader,l.update(y),le=l.getVertexShaderID(y),he=l.getFragmentShaderID(y);const Ce=s.getRenderTarget(),Oe=N.isInstancedMesh===!0,Ie=N.isBatchedMesh===!0,ze=!!y.map,te=!!y.matcap,I=!!U,ce=!!y.aoMap,ae=!!y.lightMap,se=!!y.bumpMap,de=!!y.normalMap,xe=!!y.displacementMap,pe=!!y.emissiveMap,F=!!y.metalnessMap,A=!!y.roughnessMap,j=y.anisotropy>0,ne=y.clearcoat>0,re=y.dispersion>0,ie=y.iridescence>0,Pe=y.sheen>0,me=y.transmission>0,we=j&&!!y.anisotropyMap,Ze=ne&&!!y.clearcoatMap,ue=ne&&!!y.clearcoatNormalMap,Se=ne&&!!y.clearcoatRoughnessMap,Ve=ie&&!!y.iridescenceMap,He=ie&&!!y.iridescenceThicknessMap,Te=Pe&&!!y.sheenColorMap,Je=Pe&&!!y.sheenRoughnessMap,We=!!y.specularMap,ht=!!y.specularColorMap,G=!!y.specularIntensityMap,Me=me&&!!y.transmissionMap,ee=me&&!!y.thicknessMap,oe=!!y.gradientMap,_e=!!y.alphaMap,be=y.alphaTest>0,Qe=!!y.alphaHash,Et=!!y.extensions;let jt=ei;y.toneMapped&&(Ce===null||Ce.isXRRenderTarget===!0)&&(jt=s.toneMapping);const tt={shaderID:P,shaderType:y.type,shaderName:y.name,vertexShader:W,fragmentShader:$,defines:y.defines,customVertexShaderID:le,customFragmentShaderID:he,isRawShaderMaterial:y.isRawShaderMaterial===!0,glslVersion:y.glslVersion,precision:g,batching:Ie,batchingColor:Ie&&N._colorsTexture!==null,instancing:Oe,instancingColor:Oe&&N.instanceColor!==null,instancingMorph:Oe&&N.morphTexture!==null,supportsVertexTextures:f,outputColorSpace:Ce===null?s.outputColorSpace:Ce.isXRRenderTarget===!0?Ce.texture.colorSpace:Hn,alphaToCoverage:!!y.alphaToCoverage,map:ze,matcap:te,envMap:I,envMapMode:I&&U.mapping,envMapCubeUVHeight:V,aoMap:ce,lightMap:ae,bumpMap:se,normalMap:de,displacementMap:f&&xe,emissiveMap:pe,normalMapObjectSpace:de&&y.normalMapType===Ju,normalMapTangentSpace:de&&y.normalMapType===Eh,metalnessMap:F,roughnessMap:A,anisotropy:j,anisotropyMap:we,clearcoat:ne,clearcoatMap:Ze,clearcoatNormalMap:ue,clearcoatRoughnessMap:Se,dispersion:re,iridescence:ie,iridescenceMap:Ve,iridescenceThicknessMap:He,sheen:Pe,sheenColorMap:Te,sheenRoughnessMap:Je,specularMap:We,specularColorMap:ht,specularIntensityMap:G,transmission:me,transmissionMap:Me,thicknessMap:ee,gradientMap:oe,opaque:y.transparent===!1&&y.blending===Qn&&y.alphaToCoverage===!1,alphaMap:_e,alphaTest:be,alphaHash:Qe,combine:y.combine,mapUv:ze&&p(y.map.channel),aoMapUv:ce&&p(y.aoMap.channel),lightMapUv:ae&&p(y.lightMap.channel),bumpMapUv:se&&p(y.bumpMap.channel),normalMapUv:de&&p(y.normalMap.channel),displacementMapUv:xe&&p(y.displacementMap.channel),emissiveMapUv:pe&&p(y.emissiveMap.channel),metalnessMapUv:F&&p(y.metalnessMap.channel),roughnessMapUv:A&&p(y.roughnessMap.channel),anisotropyMapUv:we&&p(y.anisotropyMap.channel),clearcoatMapUv:Ze&&p(y.clearcoatMap.channel),clearcoatNormalMapUv:ue&&p(y.clearcoatNormalMap.channel),clearcoatRoughnessMapUv:Se&&p(y.clearcoatRoughnessMap.channel),iridescenceMapUv:Ve&&p(y.iridescenceMap.channel),iridescenceThicknessMapUv:He&&p(y.iridescenceThicknessMap.channel),sheenColorMapUv:Te&&p(y.sheenColorMap.channel),sheenRoughnessMapUv:Je&&p(y.sheenRoughnessMap.channel),specularMapUv:We&&p(y.specularMap.channel),specularColorMapUv:ht&&p(y.specularColorMap.channel),specularIntensityMapUv:G&&p(y.specularIntensityMap.channel),transmissionMapUv:Me&&p(y.transmissionMap.channel),thicknessMapUv:ee&&p(y.thicknessMap.channel),alphaMapUv:_e&&p(y.alphaMap.channel),vertexTangents:!!k.attributes.tangent&&(de||j),vertexColors:y.vertexColors,vertexAlphas:y.vertexColors===!0&&!!k.attributes.color&&k.attributes.color.itemSize===4,pointsUvs:N.isPoints===!0&&!!k.attributes.uv&&(ze||_e),fog:!!B,useFog:y.fog===!0,fogExp2:!!B&&B.isFogExp2,flatShading:y.flatShading===!0,sizeAttenuation:y.sizeAttenuation===!0,logarithmicDepthBuffer:u,reverseDepthBuffer:d,skinning:N.isSkinnedMesh===!0,morphTargets:k.morphAttributes.position!==void 0,morphNormals:k.morphAttributes.normal!==void 0,morphColors:k.morphAttributes.color!==void 0,morphTargetsCount:H,morphTextureStride:Z,numDirLights:b.directional.length,numPointLights:b.point.length,numSpotLights:b.spot.length,numSpotLightMaps:b.spotLightMap.length,numRectAreaLights:b.rectArea.length,numHemiLights:b.hemi.length,numDirLightShadows:b.directionalShadowMap.length,numPointLightShadows:b.pointShadowMap.length,numSpotLightShadows:b.spotShadowMap.length,numSpotLightShadowsWithMaps:b.numSpotLightShadowsWithMaps,numLightProbes:b.numLightProbes,numClippingPlanes:o.numPlanes,numClipIntersection:o.numIntersection,dithering:y.dithering,shadowMapEnabled:s.shadowMap.enabled&&D.length>0,shadowMapType:s.shadowMap.type,toneMapping:jt,decodeVideoTexture:ze&&y.map.isVideoTexture===!0&&nt.getTransfer(y.map.colorSpace)===ut,premultipliedAlpha:y.premultipliedAlpha,doubleSided:y.side===Dt,flipSided:y.side===Ht,useDepthPacking:y.depthPacking>=0,depthPacking:y.depthPacking||0,index0AttributeName:y.index0AttributeName,extensionClipCullDistance:Et&&y.extensions.clipCullDistance===!0&&n.has("WEBGL_clip_cull_distance"),extensionMultiDraw:(Et&&y.extensions.multiDraw===!0||Ie)&&n.has("WEBGL_multi_draw"),rendererExtensionParallelShaderCompile:n.has("KHR_parallel_shader_compile"),customProgramCacheKey:y.customProgramCacheKey()};return tt.vertexUv1s=c.has(1),tt.vertexUv2s=c.has(2),tt.vertexUv3s=c.has(3),c.clear(),tt}function _(y){const b=[];if(y.shaderID?b.push(y.shaderID):(b.push(y.customVertexShaderID),b.push(y.customFragmentShaderID)),y.defines!==void 0)for(const D in y.defines)b.push(D),b.push(y.defines[D]);return y.isRawShaderMaterial===!1&&(v(b,y),M(b,y),b.push(s.outputColorSpace)),b.push(y.customProgramCacheKey),b.join()}function v(y,b){y.push(b.precision),y.push(b.outputColorSpace),y.push(b.envMapMode),y.push(b.envMapCubeUVHeight),y.push(b.mapUv),y.push(b.alphaMapUv),y.push(b.lightMapUv),y.push(b.aoMapUv),y.push(b.bumpMapUv),y.push(b.normalMapUv),y.push(b.displacementMapUv),y.push(b.emissiveMapUv),y.push(b.metalnessMapUv),y.push(b.roughnessMapUv),y.push(b.anisotropyMapUv),y.push(b.clearcoatMapUv),y.push(b.clearcoatNormalMapUv),y.push(b.clearcoatRoughnessMapUv),y.push(b.iridescenceMapUv),y.push(b.iridescenceThicknessMapUv),y.push(b.sheenColorMapUv),y.push(b.sheenRoughnessMapUv),y.push(b.specularMapUv),y.push(b.specularColorMapUv),y.push(b.specularIntensityMapUv),y.push(b.transmissionMapUv),y.push(b.thicknessMapUv),y.push(b.combine),y.push(b.fogExp2),y.push(b.sizeAttenuation),y.push(b.morphTargetsCount),y.push(b.morphAttributeCount),y.push(b.numDirLights),y.push(b.numPointLights),y.push(b.numSpotLights),y.push(b.numSpotLightMaps),y.push(b.numHemiLights),y.push(b.numRectAreaLights),y.push(b.numDirLightShadows),y.push(b.numPointLightShadows),y.push(b.numSpotLightShadows),y.push(b.numSpotLightShadowsWithMaps),y.push(b.numLightProbes),y.push(b.shadowMapType),y.push(b.toneMapping),y.push(b.numClippingPlanes),y.push(b.numClipIntersection),y.push(b.depthPacking)}function M(y,b){a.disableAll(),b.supportsVertexTextures&&a.enable(0),b.instancing&&a.enable(1),b.instancingColor&&a.enable(2),b.instancingMorph&&a.enable(3),b.matcap&&a.enable(4),b.envMap&&a.enable(5),b.normalMapObjectSpace&&a.enable(6),b.normalMapTangentSpace&&a.enable(7),b.clearcoat&&a.enable(8),b.iridescence&&a.enable(9),b.alphaTest&&a.enable(10),b.vertexColors&&a.enable(11),b.vertexAlphas&&a.enable(12),b.vertexUv1s&&a.enable(13),b.vertexUv2s&&a.enable(14),b.vertexUv3s&&a.enable(15),b.vertexTangents&&a.enable(16),b.anisotropy&&a.enable(17),b.alphaHash&&a.enable(18),b.batching&&a.enable(19),b.dispersion&&a.enable(20),b.batchingColor&&a.enable(21),y.push(a.mask),a.disableAll(),b.fog&&a.enable(0),b.useFog&&a.enable(1),b.flatShading&&a.enable(2),b.logarithmicDepthBuffer&&a.enable(3),b.reverseDepthBuffer&&a.enable(4),b.skinning&&a.enable(5),b.morphTargets&&a.enable(6),b.morphNormals&&a.enable(7),b.morphColors&&a.enable(8),b.premultipliedAlpha&&a.enable(9),b.shadowMapEnabled&&a.enable(10),b.doubleSided&&a.enable(11),b.flipSided&&a.enable(12),b.useDepthPacking&&a.enable(13),b.dithering&&a.enable(14),b.transmission&&a.enable(15),b.sheen&&a.enable(16),b.opaque&&a.enable(17),b.pointsUvs&&a.enable(18),b.decodeVideoTexture&&a.enable(19),b.alphaToCoverage&&a.enable(20),y.push(a.mask)}function S(y){const b=x[y.type];let D;if(b){const L=Sn[b];D=Is.clone(L.uniforms)}else D=y.uniforms;return D}function E(y,b){let D;for(let L=0,N=h.length;L<N;L++){const B=h[L];if(B.cacheKey===b){D=B,++D.usedTimes;break}}return D===void 0&&(D=new rg(s,b,y,r),h.push(D)),D}function C(y){if(--y.usedTimes===0){const b=h.indexOf(y);h[b]=h[h.length-1],h.pop(),y.destroy()}}function z(y){l.remove(y)}function T(){l.dispose()}return{getParameters:m,getProgramCacheKey:_,getUniforms:S,acquireProgram:E,releaseProgram:C,releaseShaderCache:z,programs:h,dispose:T}}function hg(){let s=new WeakMap;function e(o){return s.has(o)}function t(o){let a=s.get(o);return a===void 0&&(a={},s.set(o,a)),a}function n(o){s.delete(o)}function i(o,a,l){s.get(o)[a]=l}function r(){s=new WeakMap}return{has:e,get:t,remove:n,update:i,dispose:r}}function ug(s,e){return s.groupOrder!==e.groupOrder?s.groupOrder-e.groupOrder:s.renderOrder!==e.renderOrder?s.renderOrder-e.renderOrder:s.material.id!==e.material.id?s.material.id-e.material.id:s.z!==e.z?s.z-e.z:s.id-e.id}function fc(s,e){return s.groupOrder!==e.groupOrder?s.groupOrder-e.groupOrder:s.renderOrder!==e.renderOrder?s.renderOrder-e.renderOrder:s.z!==e.z?e.z-s.z:s.id-e.id}function pc(){const s=[];let e=0;const t=[],n=[],i=[];function r(){e=0,t.length=0,n.length=0,i.length=0}function o(u,d,f,g,x,p){let m=s[e];return m===void 0?(m={id:u.id,object:u,geometry:d,material:f,groupOrder:g,renderOrder:u.renderOrder,z:x,group:p},s[e]=m):(m.id=u.id,m.object=u,m.geometry=d,m.material=f,m.groupOrder=g,m.renderOrder=u.renderOrder,m.z=x,m.group=p),e++,m}function a(u,d,f,g,x,p){const m=o(u,d,f,g,x,p);f.transmission>0?n.push(m):f.transparent===!0?i.push(m):t.push(m)}function l(u,d,f,g,x,p){const m=o(u,d,f,g,x,p);f.transmission>0?n.unshift(m):f.transparent===!0?i.unshift(m):t.unshift(m)}function c(u,d){t.length>1&&t.sort(u||ug),n.length>1&&n.sort(d||fc),i.length>1&&i.sort(d||fc)}function h(){for(let u=e,d=s.length;u<d;u++){const f=s[u];if(f.id===null)break;f.id=null,f.object=null,f.geometry=null,f.material=null,f.group=null}}return{opaque:t,transmissive:n,transparent:i,init:r,push:a,unshift:l,finish:h,sort:c}}function dg(){let s=new WeakMap;function e(n,i){const r=s.get(n);let o;return r===void 0?(o=new pc,s.set(n,[o])):i>=r.length?(o=new pc,r.push(o)):o=r[i],o}function t(){s=new WeakMap}return{get:e,dispose:t}}function fg(){const s={};return{get:function(e){if(s[e.id]!==void 0)return s[e.id];let t;switch(e.type){case"DirectionalLight":t={direction:new w,color:new Ne};break;case"SpotLight":t={position:new w,direction:new w,color:new Ne,distance:0,coneCos:0,penumbraCos:0,decay:0};break;case"PointLight":t={position:new w,color:new Ne,distance:0,decay:0};break;case"HemisphereLight":t={direction:new w,skyColor:new Ne,groundColor:new Ne};break;case"RectAreaLight":t={color:new Ne,position:new w,halfWidth:new w,halfHeight:new w};break}return s[e.id]=t,t}}}function pg(){const s={};return{get:function(e){if(s[e.id]!==void 0)return s[e.id];let t;switch(e.type){case"DirectionalLight":t={shadowIntensity:1,shadowBias:0,shadowNormalBias:0,shadowRadius:1,shadowMapSize:new Q};break;case"SpotLight":t={shadowIntensity:1,shadowBias:0,shadowNormalBias:0,shadowRadius:1,shadowMapSize:new Q};break;case"PointLight":t={shadowIntensity:1,shadowBias:0,shadowNormalBias:0,shadowRadius:1,shadowMapSize:new Q,shadowCameraNear:1,shadowCameraFar:1e3};break}return s[e.id]=t,t}}}let mg=0;function gg(s,e){return(e.castShadow?2:0)-(s.castShadow?2:0)+(e.map?1:0)-(s.map?1:0)}function vg(s){const e=new fg,t=pg(),n={version:0,hash:{directionalLength:-1,pointLength:-1,spotLength:-1,rectAreaLength:-1,hemiLength:-1,numDirectionalShadows:-1,numPointShadows:-1,numSpotShadows:-1,numSpotMaps:-1,numLightProbes:-1},ambient:[0,0,0],probe:[],directional:[],directionalShadow:[],directionalShadowMap:[],directionalShadowMatrix:[],spot:[],spotLightMap:[],spotShadow:[],spotShadowMap:[],spotLightMatrix:[],rectArea:[],rectAreaLTC1:null,rectAreaLTC2:null,point:[],pointShadow:[],pointShadowMap:[],pointShadowMatrix:[],hemi:[],numSpotLightShadowsWithMaps:0,numLightProbes:0};for(let c=0;c<9;c++)n.probe.push(new w);const i=new w,r=new Fe,o=new Fe;function a(c){let h=0,u=0,d=0;for(let T=0;T<9;T++)n.probe[T].set(0,0,0);let f=0,g=0,x=0,p=0,m=0,_=0,v=0,M=0,S=0,E=0,C=0;c.sort(gg);for(let T=0,y=c.length;T<y;T++){const b=c[T],D=b.color,L=b.intensity,N=b.distance,B=b.shadow&&b.shadow.map?b.shadow.map.texture:null;if(b.isAmbientLight)h+=D.r*L,u+=D.g*L,d+=D.b*L;else if(b.isLightProbe){for(let k=0;k<9;k++)n.probe[k].addScaledVector(b.sh.coefficients[k],L);C++}else if(b.isDirectionalLight){const k=e.get(b);if(k.color.copy(b.color).multiplyScalar(b.intensity),b.castShadow){const q=b.shadow,U=t.get(b);U.shadowIntensity=q.intensity,U.shadowBias=q.bias,U.shadowNormalBias=q.normalBias,U.shadowRadius=q.radius,U.shadowMapSize=q.mapSize,n.directionalShadow[f]=U,n.directionalShadowMap[f]=B,n.directionalShadowMatrix[f]=b.shadow.matrix,_++}n.directional[f]=k,f++}else if(b.isSpotLight){const k=e.get(b);k.position.setFromMatrixPosition(b.matrixWorld),k.color.copy(D).multiplyScalar(L),k.distance=N,k.coneCos=Math.cos(b.angle),k.penumbraCos=Math.cos(b.angle*(1-b.penumbra)),k.decay=b.decay,n.spot[x]=k;const q=b.shadow;if(b.map&&(n.spotLightMap[S]=b.map,S++,q.updateMatrices(b),b.castShadow&&E++),n.spotLightMatrix[x]=q.matrix,b.castShadow){const U=t.get(b);U.shadowIntensity=q.intensity,U.shadowBias=q.bias,U.shadowNormalBias=q.normalBias,U.shadowRadius=q.radius,U.shadowMapSize=q.mapSize,n.spotShadow[x]=U,n.spotShadowMap[x]=B,M++}x++}else if(b.isRectAreaLight){const k=e.get(b);k.color.copy(D).multiplyScalar(L),k.halfWidth.set(b.width*.5,0,0),k.halfHeight.set(0,b.height*.5,0),n.rectArea[p]=k,p++}else if(b.isPointLight){const k=e.get(b);if(k.color.copy(b.color).multiplyScalar(b.intensity),k.distance=b.distance,k.decay=b.decay,b.castShadow){const q=b.shadow,U=t.get(b);U.shadowIntensity=q.intensity,U.shadowBias=q.bias,U.shadowNormalBias=q.normalBias,U.shadowRadius=q.radius,U.shadowMapSize=q.mapSize,U.shadowCameraNear=q.camera.near,U.shadowCameraFar=q.camera.far,n.pointShadow[g]=U,n.pointShadowMap[g]=B,n.pointShadowMatrix[g]=b.shadow.matrix,v++}n.point[g]=k,g++}else if(b.isHemisphereLight){const k=e.get(b);k.skyColor.copy(b.color).multiplyScalar(L),k.groundColor.copy(b.groundColor).multiplyScalar(L),n.hemi[m]=k,m++}}p>0&&(s.has("OES_texture_float_linear")===!0?(n.rectAreaLTC1=ge.LTC_FLOAT_1,n.rectAreaLTC2=ge.LTC_FLOAT_2):(n.rectAreaLTC1=ge.LTC_HALF_1,n.rectAreaLTC2=ge.LTC_HALF_2)),n.ambient[0]=h,n.ambient[1]=u,n.ambient[2]=d;const z=n.hash;(z.directionalLength!==f||z.pointLength!==g||z.spotLength!==x||z.rectAreaLength!==p||z.hemiLength!==m||z.numDirectionalShadows!==_||z.numPointShadows!==v||z.numSpotShadows!==M||z.numSpotMaps!==S||z.numLightProbes!==C)&&(n.directional.length=f,n.spot.length=x,n.rectArea.length=p,n.point.length=g,n.hemi.length=m,n.directionalShadow.length=_,n.directionalShadowMap.length=_,n.pointShadow.length=v,n.pointShadowMap.length=v,n.spotShadow.length=M,n.spotShadowMap.length=M,n.directionalShadowMatrix.length=_,n.pointShadowMatrix.length=v,n.spotLightMatrix.length=M+S-E,n.spotLightMap.length=S,n.numSpotLightShadowsWithMaps=E,n.numLightProbes=C,z.directionalLength=f,z.pointLength=g,z.spotLength=x,z.rectAreaLength=p,z.hemiLength=m,z.numDirectionalShadows=_,z.numPointShadows=v,z.numSpotShadows=M,z.numSpotMaps=S,z.numLightProbes=C,n.version=mg++)}function l(c,h){let u=0,d=0,f=0,g=0,x=0;const p=h.matrixWorldInverse;for(let m=0,_=c.length;m<_;m++){const v=c[m];if(v.isDirectionalLight){const M=n.directional[u];M.direction.setFromMatrixPosition(v.matrixWorld),i.setFromMatrixPosition(v.target.matrixWorld),M.direction.sub(i),M.direction.transformDirection(p),u++}else if(v.isSpotLight){const M=n.spot[f];M.position.setFromMatrixPosition(v.matrixWorld),M.position.applyMatrix4(p),M.direction.setFromMatrixPosition(v.matrixWorld),i.setFromMatrixPosition(v.target.matrixWorld),M.direction.sub(i),M.direction.transformDirection(p),f++}else if(v.isRectAreaLight){const M=n.rectArea[g];M.position.setFromMatrixPosition(v.matrixWorld),M.position.applyMatrix4(p),o.identity(),r.copy(v.matrixWorld),r.premultiply(p),o.extractRotation(r),M.halfWidth.set(v.width*.5,0,0),M.halfHeight.set(0,v.height*.5,0),M.halfWidth.applyMatrix4(o),M.halfHeight.applyMatrix4(o),g++}else if(v.isPointLight){const M=n.point[d];M.position.setFromMatrixPosition(v.matrixWorld),M.position.applyMatrix4(p),d++}else if(v.isHemisphereLight){const M=n.hemi[x];M.direction.setFromMatrixPosition(v.matrixWorld),M.direction.transformDirection(p),x++}}}return{setup:a,setupView:l,state:n}}function mc(s){const e=new vg(s),t=[],n=[];function i(h){c.camera=h,t.length=0,n.length=0}function r(h){t.push(h)}function o(h){n.push(h)}function a(){e.setup(t)}function l(h){e.setupView(t,h)}const c={lightsArray:t,shadowsArray:n,camera:null,lights:e,transmissionRenderTarget:{}};return{init:i,state:c,setupLights:a,setupLightsView:l,pushLight:r,pushShadow:o}}function xg(s){let e=new WeakMap;function t(i,r=0){const o=e.get(i);let a;return o===void 0?(a=new mc(s),e.set(i,[a])):r>=o.length?(a=new mc(s),o.push(a)):a=o[r],a}function n(){e=new WeakMap}return{get:t,dispose:n}}class _g extends wi{constructor(e){super(),this.isMeshDepthMaterial=!0,this.type="MeshDepthMaterial",this.depthPacking=Ku,this.map=null,this.alphaMap=null,this.displacementMap=null,this.displacementScale=1,this.displacementBias=0,this.wireframe=!1,this.wireframeLinewidth=1,this.setValues(e)}copy(e){return super.copy(e),this.depthPacking=e.depthPacking,this.map=e.map,this.alphaMap=e.alphaMap,this.displacementMap=e.displacementMap,this.displacementScale=e.displacementScale,this.displacementBias=e.displacementBias,this.wireframe=e.wireframe,this.wireframeLinewidth=e.wireframeLinewidth,this}}class yg extends wi{constructor(e){super(),this.isMeshDistanceMaterial=!0,this.type="MeshDistanceMaterial",this.map=null,this.alphaMap=null,this.displacementMap=null,this.displacementScale=1,this.displacementBias=0,this.setValues(e)}copy(e){return super.copy(e),this.map=e.map,this.alphaMap=e.alphaMap,this.displacementMap=e.displacementMap,this.displacementScale=e.displacementScale,this.displacementBias=e.displacementBias,this}}const Mg=`void main() {
	gl_Position = vec4( position, 1.0 );
}`,bg=`uniform sampler2D shadow_pass;
uniform vec2 resolution;
uniform float radius;
#include <packing>
void main() {
	const float samples = float( VSM_SAMPLES );
	float mean = 0.0;
	float squared_mean = 0.0;
	float uvStride = samples <= 1.0 ? 0.0 : 2.0 / ( samples - 1.0 );
	float uvStart = samples <= 1.0 ? 0.0 : - 1.0;
	for ( float i = 0.0; i < samples; i ++ ) {
		float uvOffset = uvStart + i * uvStride;
		#ifdef HORIZONTAL_PASS
			vec2 distribution = unpackRGBATo2Half( texture2D( shadow_pass, ( gl_FragCoord.xy + vec2( uvOffset, 0.0 ) * radius ) / resolution ) );
			mean += distribution.x;
			squared_mean += distribution.y * distribution.y + distribution.x * distribution.x;
		#else
			float depth = unpackRGBAToDepth( texture2D( shadow_pass, ( gl_FragCoord.xy + vec2( 0.0, uvOffset ) * radius ) / resolution ) );
			mean += depth;
			squared_mean += depth * depth;
		#endif
	}
	mean = mean / samples;
	squared_mean = squared_mean / samples;
	float std_dev = sqrt( squared_mean - mean * mean );
	gl_FragColor = pack2HalfToRGBA( vec2( mean, std_dev ) );
}`;function wg(s,e,t){let n=new el;const i=new Q,r=new Q,o=new ot,a=new _g({depthPacking:Zu}),l=new yg,c={},h=t.maxTextureSize,u={[wn]:Ht,[Ht]:wn,[Dt]:Dt},d=new gt({defines:{VSM_SAMPLES:8},uniforms:{shadow_pass:{value:null},resolution:{value:new Q},radius:{value:4}},vertexShader:Mg,fragmentShader:bg}),f=d.clone();f.defines.HORIZONTAL_PASS=1;const g=new je;g.setAttribute("position",new kt(new Float32Array([-1,-1,.5,3,-1,.5,-1,3,.5]),3));const x=new ve(g,d),p=this;this.enabled=!1,this.autoUpdate=!0,this.needsUpdate=!1,this.type=lh;let m=this.type;this.render=function(E,C,z){if(p.enabled===!1||p.autoUpdate===!1&&p.needsUpdate===!1||E.length===0)return;const T=s.getRenderTarget(),y=s.getActiveCubeFace(),b=s.getActiveMipmapLevel(),D=s.state;D.setBlending(kn),D.buffers.color.setClear(1,1,1,1),D.buffers.depth.setTest(!0),D.setScissorTest(!1);const L=m!==Un&&this.type===Un,N=m===Un&&this.type!==Un;for(let B=0,k=E.length;B<k;B++){const q=E[B],U=q.shadow;if(U===void 0){console.warn("THREE.WebGLShadowMap:",q,"has no shadow.");continue}if(U.autoUpdate===!1&&U.needsUpdate===!1)continue;i.copy(U.mapSize);const V=U.getFrameExtents();if(i.multiply(V),r.copy(U.mapSize),(i.x>h||i.y>h)&&(i.x>h&&(r.x=Math.floor(h/V.x),i.x=r.x*V.x,U.mapSize.x=r.x),i.y>h&&(r.y=Math.floor(h/V.y),i.y=r.y*V.y,U.mapSize.y=r.y)),U.map===null||L===!0||N===!0){const O=this.type!==Un?{minFilter:$t,magFilter:$t}:{};U.map!==null&&U.map.dispose(),U.map=new un(i.x,i.y,O),U.map.texture.name=q.name+".shadowMap",U.camera.updateProjectionMatrix()}s.setRenderTarget(U.map),s.clear();const P=U.getViewportCount();for(let O=0;O<P;O++){const H=U.getViewport(O);o.set(r.x*H.x,r.y*H.y,r.x*H.z,r.y*H.w),D.viewport(o),U.updateMatrices(q,O),n=U.getFrustum(),M(C,z,U.camera,q,this.type)}U.isPointLightShadow!==!0&&this.type===Un&&_(U,z),U.needsUpdate=!1}m=this.type,p.needsUpdate=!1,s.setRenderTarget(T,y,b)};function _(E,C){const z=e.update(x);d.defines.VSM_SAMPLES!==E.blurSamples&&(d.defines.VSM_SAMPLES=E.blurSamples,f.defines.VSM_SAMPLES=E.blurSamples,d.needsUpdate=!0,f.needsUpdate=!0),E.mapPass===null&&(E.mapPass=new un(i.x,i.y)),d.uniforms.shadow_pass.value=E.map.texture,d.uniforms.resolution.value=E.mapSize,d.uniforms.radius.value=E.radius,s.setRenderTarget(E.mapPass),s.clear(),s.renderBufferDirect(C,null,z,d,x,null),f.uniforms.shadow_pass.value=E.mapPass.texture,f.uniforms.resolution.value=E.mapSize,f.uniforms.radius.value=E.radius,s.setRenderTarget(E.map),s.clear(),s.renderBufferDirect(C,null,z,f,x,null)}function v(E,C,z,T){let y=null;const b=z.isPointLight===!0?E.customDistanceMaterial:E.customDepthMaterial;if(b!==void 0)y=b;else if(y=z.isPointLight===!0?l:a,s.localClippingEnabled&&C.clipShadows===!0&&Array.isArray(C.clippingPlanes)&&C.clippingPlanes.length!==0||C.displacementMap&&C.displacementScale!==0||C.alphaMap&&C.alphaTest>0||C.map&&C.alphaTest>0){const D=y.uuid,L=C.uuid;let N=c[D];N===void 0&&(N={},c[D]=N);let B=N[L];B===void 0&&(B=y.clone(),N[L]=B,C.addEventListener("dispose",S)),y=B}if(y.visible=C.visible,y.wireframe=C.wireframe,T===Un?y.side=C.shadowSide!==null?C.shadowSide:C.side:y.side=C.shadowSide!==null?C.shadowSide:u[C.side],y.alphaMap=C.alphaMap,y.alphaTest=C.alphaTest,y.map=C.map,y.clipShadows=C.clipShadows,y.clippingPlanes=C.clippingPlanes,y.clipIntersection=C.clipIntersection,y.displacementMap=C.displacementMap,y.displacementScale=C.displacementScale,y.displacementBias=C.displacementBias,y.wireframeLinewidth=C.wireframeLinewidth,y.linewidth=C.linewidth,z.isPointLight===!0&&y.isMeshDistanceMaterial===!0){const D=s.properties.get(y);D.light=z}return y}function M(E,C,z,T,y){if(E.visible===!1)return;if(E.layers.test(C.layers)&&(E.isMesh||E.isLine||E.isPoints)&&(E.castShadow||E.receiveShadow&&y===Un)&&(!E.frustumCulled||n.intersectsObject(E))){E.modelViewMatrix.multiplyMatrices(z.matrixWorldInverse,E.matrixWorld);const L=e.update(E),N=E.material;if(Array.isArray(N)){const B=L.groups;for(let k=0,q=B.length;k<q;k++){const U=B[k],V=N[U.materialIndex];if(V&&V.visible){const P=v(E,V,T,y);E.onBeforeShadow(s,E,C,z,L,P,U),s.renderBufferDirect(z,null,L,P,E,U),E.onAfterShadow(s,E,C,z,L,P,U)}}}else if(N.visible){const B=v(E,N,T,y);E.onBeforeShadow(s,E,C,z,L,B,null),s.renderBufferDirect(z,null,L,B,E,null),E.onAfterShadow(s,E,C,z,L,B,null)}}const D=E.children;for(let L=0,N=D.length;L<N;L++)M(D[L],C,z,T,y)}function S(E){E.target.removeEventListener("dispose",S);for(const z in c){const T=c[z],y=E.target.uuid;y in T&&(T[y].dispose(),delete T[y])}}}const Sg={[jo]:Ko,[Zo]:Qo,[Jo]:ea,[Ji]:$o,[Ko]:jo,[Qo]:Zo,[ea]:Jo,[$o]:Ji};function Tg(s){function e(){let G=!1;const Me=new ot;let ee=null;const oe=new ot(0,0,0,0);return{setMask:function(_e){ee!==_e&&!G&&(s.colorMask(_e,_e,_e,_e),ee=_e)},setLocked:function(_e){G=_e},setClear:function(_e,be,Qe,Et,jt){jt===!0&&(_e*=Et,be*=Et,Qe*=Et),Me.set(_e,be,Qe,Et),oe.equals(Me)===!1&&(s.clearColor(_e,be,Qe,Et),oe.copy(Me))},reset:function(){G=!1,ee=null,oe.set(-1,0,0,0)}}}function t(){let G=!1,Me=!1,ee=null,oe=null,_e=null;return{setReversed:function(be){Me=be},setTest:function(be){be?le(s.DEPTH_TEST):he(s.DEPTH_TEST)},setMask:function(be){ee!==be&&!G&&(s.depthMask(be),ee=be)},setFunc:function(be){if(Me&&(be=Sg[be]),oe!==be){switch(be){case jo:s.depthFunc(s.NEVER);break;case Ko:s.depthFunc(s.ALWAYS);break;case Zo:s.depthFunc(s.LESS);break;case Ji:s.depthFunc(s.LEQUAL);break;case Jo:s.depthFunc(s.EQUAL);break;case $o:s.depthFunc(s.GEQUAL);break;case Qo:s.depthFunc(s.GREATER);break;case ea:s.depthFunc(s.NOTEQUAL);break;default:s.depthFunc(s.LEQUAL)}oe=be}},setLocked:function(be){G=be},setClear:function(be){_e!==be&&(s.clearDepth(be),_e=be)},reset:function(){G=!1,ee=null,oe=null,_e=null}}}function n(){let G=!1,Me=null,ee=null,oe=null,_e=null,be=null,Qe=null,Et=null,jt=null;return{setTest:function(tt){G||(tt?le(s.STENCIL_TEST):he(s.STENCIL_TEST))},setMask:function(tt){Me!==tt&&!G&&(s.stencilMask(tt),Me=tt)},setFunc:function(tt,Kt,Cn){(ee!==tt||oe!==Kt||_e!==Cn)&&(s.stencilFunc(tt,Kt,Cn),ee=tt,oe=Kt,_e=Cn)},setOp:function(tt,Kt,Cn){(be!==tt||Qe!==Kt||Et!==Cn)&&(s.stencilOp(tt,Kt,Cn),be=tt,Qe=Kt,Et=Cn)},setLocked:function(tt){G=tt},setClear:function(tt){jt!==tt&&(s.clearStencil(tt),jt=tt)},reset:function(){G=!1,Me=null,ee=null,oe=null,_e=null,be=null,Qe=null,Et=null,jt=null}}}const i=new e,r=new t,o=new n,a=new WeakMap,l=new WeakMap;let c={},h={},u=new WeakMap,d=[],f=null,g=!1,x=null,p=null,m=null,_=null,v=null,M=null,S=null,E=new Ne(0,0,0),C=0,z=!1,T=null,y=null,b=null,D=null,L=null;const N=s.getParameter(s.MAX_COMBINED_TEXTURE_IMAGE_UNITS);let B=!1,k=0;const q=s.getParameter(s.VERSION);q.indexOf("WebGL")!==-1?(k=parseFloat(/^WebGL (\d)/.exec(q)[1]),B=k>=1):q.indexOf("OpenGL ES")!==-1&&(k=parseFloat(/^OpenGL ES (\d)/.exec(q)[1]),B=k>=2);let U=null,V={};const P=s.getParameter(s.SCISSOR_BOX),O=s.getParameter(s.VIEWPORT),H=new ot().fromArray(P),Z=new ot().fromArray(O);function W(G,Me,ee,oe){const _e=new Uint8Array(4),be=s.createTexture();s.bindTexture(G,be),s.texParameteri(G,s.TEXTURE_MIN_FILTER,s.NEAREST),s.texParameteri(G,s.TEXTURE_MAG_FILTER,s.NEAREST);for(let Qe=0;Qe<ee;Qe++)G===s.TEXTURE_3D||G===s.TEXTURE_2D_ARRAY?s.texImage3D(Me,0,s.RGBA,1,1,oe,0,s.RGBA,s.UNSIGNED_BYTE,_e):s.texImage2D(Me+Qe,0,s.RGBA,1,1,0,s.RGBA,s.UNSIGNED_BYTE,_e);return be}const $={};$[s.TEXTURE_2D]=W(s.TEXTURE_2D,s.TEXTURE_2D,1),$[s.TEXTURE_CUBE_MAP]=W(s.TEXTURE_CUBE_MAP,s.TEXTURE_CUBE_MAP_POSITIVE_X,6),$[s.TEXTURE_2D_ARRAY]=W(s.TEXTURE_2D_ARRAY,s.TEXTURE_2D_ARRAY,1,1),$[s.TEXTURE_3D]=W(s.TEXTURE_3D,s.TEXTURE_3D,1,1),i.setClear(0,0,0,1),r.setClear(1),o.setClear(0),le(s.DEPTH_TEST),r.setFunc(Ji),ae(!1),se(Sl),le(s.CULL_FACE),I(kn);function le(G){c[G]!==!0&&(s.enable(G),c[G]=!0)}function he(G){c[G]!==!1&&(s.disable(G),c[G]=!1)}function Ce(G,Me){return h[G]!==Me?(s.bindFramebuffer(G,Me),h[G]=Me,G===s.DRAW_FRAMEBUFFER&&(h[s.FRAMEBUFFER]=Me),G===s.FRAMEBUFFER&&(h[s.DRAW_FRAMEBUFFER]=Me),!0):!1}function Oe(G,Me){let ee=d,oe=!1;if(G){ee=u.get(Me),ee===void 0&&(ee=[],u.set(Me,ee));const _e=G.textures;if(ee.length!==_e.length||ee[0]!==s.COLOR_ATTACHMENT0){for(let be=0,Qe=_e.length;be<Qe;be++)ee[be]=s.COLOR_ATTACHMENT0+be;ee.length=_e.length,oe=!0}}else ee[0]!==s.BACK&&(ee[0]=s.BACK,oe=!0);oe&&s.drawBuffers(ee)}function Ie(G){return f!==G?(s.useProgram(G),f=G,!0):!1}const ze={[ui]:s.FUNC_ADD,[Cu]:s.FUNC_SUBTRACT,[Pu]:s.FUNC_REVERSE_SUBTRACT};ze[Ru]=s.MIN,ze[Du]=s.MAX;const te={[Iu]:s.ZERO,[Lu]:s.ONE,[Nu]:s.SRC_COLOR,[Yo]:s.SRC_ALPHA,[Bu]:s.SRC_ALPHA_SATURATE,[zu]:s.DST_COLOR,[Ou]:s.DST_ALPHA,[Uu]:s.ONE_MINUS_SRC_COLOR,[qo]:s.ONE_MINUS_SRC_ALPHA,[ku]:s.ONE_MINUS_DST_COLOR,[Fu]:s.ONE_MINUS_DST_ALPHA,[Vu]:s.CONSTANT_COLOR,[Hu]:s.ONE_MINUS_CONSTANT_COLOR,[Gu]:s.CONSTANT_ALPHA,[Wu]:s.ONE_MINUS_CONSTANT_ALPHA};function I(G,Me,ee,oe,_e,be,Qe,Et,jt,tt){if(G===kn){g===!0&&(he(s.BLEND),g=!1);return}if(g===!1&&(le(s.BLEND),g=!0),G!==Au){if(G!==x||tt!==z){if((p!==ui||v!==ui)&&(s.blendEquation(s.FUNC_ADD),p=ui,v=ui),tt)switch(G){case Qn:s.blendFuncSeparate(s.ONE,s.ONE_MINUS_SRC_ALPHA,s.ONE,s.ONE_MINUS_SRC_ALPHA);break;case Mn:s.blendFunc(s.ONE,s.ONE);break;case Tl:s.blendFuncSeparate(s.ZERO,s.ONE_MINUS_SRC_COLOR,s.ZERO,s.ONE);break;case El:s.blendFuncSeparate(s.ZERO,s.SRC_COLOR,s.ZERO,s.SRC_ALPHA);break;default:console.error("THREE.WebGLState: Invalid blending: ",G);break}else switch(G){case Qn:s.blendFuncSeparate(s.SRC_ALPHA,s.ONE_MINUS_SRC_ALPHA,s.ONE,s.ONE_MINUS_SRC_ALPHA);break;case Mn:s.blendFunc(s.SRC_ALPHA,s.ONE);break;case Tl:s.blendFuncSeparate(s.ZERO,s.ONE_MINUS_SRC_COLOR,s.ZERO,s.ONE);break;case El:s.blendFunc(s.ZERO,s.SRC_COLOR);break;default:console.error("THREE.WebGLState: Invalid blending: ",G);break}m=null,_=null,M=null,S=null,E.set(0,0,0),C=0,x=G,z=tt}return}_e=_e||Me,be=be||ee,Qe=Qe||oe,(Me!==p||_e!==v)&&(s.blendEquationSeparate(ze[Me],ze[_e]),p=Me,v=_e),(ee!==m||oe!==_||be!==M||Qe!==S)&&(s.blendFuncSeparate(te[ee],te[oe],te[be],te[Qe]),m=ee,_=oe,M=be,S=Qe),(Et.equals(E)===!1||jt!==C)&&(s.blendColor(Et.r,Et.g,Et.b,jt),E.copy(Et),C=jt),x=G,z=!1}function ce(G,Me){G.side===Dt?he(s.CULL_FACE):le(s.CULL_FACE);let ee=G.side===Ht;Me&&(ee=!ee),ae(ee),G.blending===Qn&&G.transparent===!1?I(kn):I(G.blending,G.blendEquation,G.blendSrc,G.blendDst,G.blendEquationAlpha,G.blendSrcAlpha,G.blendDstAlpha,G.blendColor,G.blendAlpha,G.premultipliedAlpha),r.setFunc(G.depthFunc),r.setTest(G.depthTest),r.setMask(G.depthWrite),i.setMask(G.colorWrite);const oe=G.stencilWrite;o.setTest(oe),oe&&(o.setMask(G.stencilWriteMask),o.setFunc(G.stencilFunc,G.stencilRef,G.stencilFuncMask),o.setOp(G.stencilFail,G.stencilZFail,G.stencilZPass)),xe(G.polygonOffset,G.polygonOffsetFactor,G.polygonOffsetUnits),G.alphaToCoverage===!0?le(s.SAMPLE_ALPHA_TO_COVERAGE):he(s.SAMPLE_ALPHA_TO_COVERAGE)}function ae(G){T!==G&&(G?s.frontFace(s.CW):s.frontFace(s.CCW),T=G)}function se(G){G!==Tu?(le(s.CULL_FACE),G!==y&&(G===Sl?s.cullFace(s.BACK):G===Eu?s.cullFace(s.FRONT):s.cullFace(s.FRONT_AND_BACK))):he(s.CULL_FACE),y=G}function de(G){G!==b&&(B&&s.lineWidth(G),b=G)}function xe(G,Me,ee){G?(le(s.POLYGON_OFFSET_FILL),(D!==Me||L!==ee)&&(s.polygonOffset(Me,ee),D=Me,L=ee)):he(s.POLYGON_OFFSET_FILL)}function pe(G){G?le(s.SCISSOR_TEST):he(s.SCISSOR_TEST)}function F(G){G===void 0&&(G=s.TEXTURE0+N-1),U!==G&&(s.activeTexture(G),U=G)}function A(G,Me,ee){ee===void 0&&(U===null?ee=s.TEXTURE0+N-1:ee=U);let oe=V[ee];oe===void 0&&(oe={type:void 0,texture:void 0},V[ee]=oe),(oe.type!==G||oe.texture!==Me)&&(U!==ee&&(s.activeTexture(ee),U=ee),s.bindTexture(G,Me||$[G]),oe.type=G,oe.texture=Me)}function j(){const G=V[U];G!==void 0&&G.type!==void 0&&(s.bindTexture(G.type,null),G.type=void 0,G.texture=void 0)}function ne(){try{s.compressedTexImage2D.apply(s,arguments)}catch(G){console.error("THREE.WebGLState:",G)}}function re(){try{s.compressedTexImage3D.apply(s,arguments)}catch(G){console.error("THREE.WebGLState:",G)}}function ie(){try{s.texSubImage2D.apply(s,arguments)}catch(G){console.error("THREE.WebGLState:",G)}}function Pe(){try{s.texSubImage3D.apply(s,arguments)}catch(G){console.error("THREE.WebGLState:",G)}}function me(){try{s.compressedTexSubImage2D.apply(s,arguments)}catch(G){console.error("THREE.WebGLState:",G)}}function we(){try{s.compressedTexSubImage3D.apply(s,arguments)}catch(G){console.error("THREE.WebGLState:",G)}}function Ze(){try{s.texStorage2D.apply(s,arguments)}catch(G){console.error("THREE.WebGLState:",G)}}function ue(){try{s.texStorage3D.apply(s,arguments)}catch(G){console.error("THREE.WebGLState:",G)}}function Se(){try{s.texImage2D.apply(s,arguments)}catch(G){console.error("THREE.WebGLState:",G)}}function Ve(){try{s.texImage3D.apply(s,arguments)}catch(G){console.error("THREE.WebGLState:",G)}}function He(G){H.equals(G)===!1&&(s.scissor(G.x,G.y,G.z,G.w),H.copy(G))}function Te(G){Z.equals(G)===!1&&(s.viewport(G.x,G.y,G.z,G.w),Z.copy(G))}function Je(G,Me){let ee=l.get(Me);ee===void 0&&(ee=new WeakMap,l.set(Me,ee));let oe=ee.get(G);oe===void 0&&(oe=s.getUniformBlockIndex(Me,G.name),ee.set(G,oe))}function We(G,Me){const oe=l.get(Me).get(G);a.get(Me)!==oe&&(s.uniformBlockBinding(Me,oe,G.__bindingPointIndex),a.set(Me,oe))}function ht(){s.disable(s.BLEND),s.disable(s.CULL_FACE),s.disable(s.DEPTH_TEST),s.disable(s.POLYGON_OFFSET_FILL),s.disable(s.SCISSOR_TEST),s.disable(s.STENCIL_TEST),s.disable(s.SAMPLE_ALPHA_TO_COVERAGE),s.blendEquation(s.FUNC_ADD),s.blendFunc(s.ONE,s.ZERO),s.blendFuncSeparate(s.ONE,s.ZERO,s.ONE,s.ZERO),s.blendColor(0,0,0,0),s.colorMask(!0,!0,!0,!0),s.clearColor(0,0,0,0),s.depthMask(!0),s.depthFunc(s.LESS),s.clearDepth(1),s.stencilMask(4294967295),s.stencilFunc(s.ALWAYS,0,4294967295),s.stencilOp(s.KEEP,s.KEEP,s.KEEP),s.clearStencil(0),s.cullFace(s.BACK),s.frontFace(s.CCW),s.polygonOffset(0,0),s.activeTexture(s.TEXTURE0),s.bindFramebuffer(s.FRAMEBUFFER,null),s.bindFramebuffer(s.DRAW_FRAMEBUFFER,null),s.bindFramebuffer(s.READ_FRAMEBUFFER,null),s.useProgram(null),s.lineWidth(1),s.scissor(0,0,s.canvas.width,s.canvas.height),s.viewport(0,0,s.canvas.width,s.canvas.height),c={},U=null,V={},h={},u=new WeakMap,d=[],f=null,g=!1,x=null,p=null,m=null,_=null,v=null,M=null,S=null,E=new Ne(0,0,0),C=0,z=!1,T=null,y=null,b=null,D=null,L=null,H.set(0,0,s.canvas.width,s.canvas.height),Z.set(0,0,s.canvas.width,s.canvas.height),i.reset(),r.reset(),o.reset()}return{buffers:{color:i,depth:r,stencil:o},enable:le,disable:he,bindFramebuffer:Ce,drawBuffers:Oe,useProgram:Ie,setBlending:I,setMaterial:ce,setFlipSided:ae,setCullFace:se,setLineWidth:de,setPolygonOffset:xe,setScissorTest:pe,activeTexture:F,bindTexture:A,unbindTexture:j,compressedTexImage2D:ne,compressedTexImage3D:re,texImage2D:Se,texImage3D:Ve,updateUBOMapping:Je,uniformBlockBinding:We,texStorage2D:Ze,texStorage3D:ue,texSubImage2D:ie,texSubImage3D:Pe,compressedTexSubImage2D:me,compressedTexSubImage3D:we,scissor:He,viewport:Te,reset:ht}}function gc(s,e,t,n){const i=Eg(n);switch(t){case yh:return s*e;case bh:return s*e;case wh:return s*e*2;case qa:return s*e/i.components*i.byteLength;case ja:return s*e/i.components*i.byteLength;case Sh:return s*e*2/i.components*i.byteLength;case Ka:return s*e*2/i.components*i.byteLength;case Mh:return s*e*3/i.components*i.byteLength;case sn:return s*e*4/i.components*i.byteLength;case Za:return s*e*4/i.components*i.byteLength;case wr:case Sr:return Math.floor((s+3)/4)*Math.floor((e+3)/4)*8;case Tr:case Er:return Math.floor((s+3)/4)*Math.floor((e+3)/4)*16;case ra:case aa:return Math.max(s,16)*Math.max(e,8)/4;case sa:case oa:return Math.max(s,8)*Math.max(e,8)/2;case la:case ca:return Math.floor((s+3)/4)*Math.floor((e+3)/4)*8;case ha:return Math.floor((s+3)/4)*Math.floor((e+3)/4)*16;case ua:return Math.floor((s+3)/4)*Math.floor((e+3)/4)*16;case da:return Math.floor((s+4)/5)*Math.floor((e+3)/4)*16;case fa:return Math.floor((s+4)/5)*Math.floor((e+4)/5)*16;case pa:return Math.floor((s+5)/6)*Math.floor((e+4)/5)*16;case ma:return Math.floor((s+5)/6)*Math.floor((e+5)/6)*16;case ga:return Math.floor((s+7)/8)*Math.floor((e+4)/5)*16;case va:return Math.floor((s+7)/8)*Math.floor((e+5)/6)*16;case xa:return Math.floor((s+7)/8)*Math.floor((e+7)/8)*16;case _a:return Math.floor((s+9)/10)*Math.floor((e+4)/5)*16;case ya:return Math.floor((s+9)/10)*Math.floor((e+5)/6)*16;case Ma:return Math.floor((s+9)/10)*Math.floor((e+7)/8)*16;case ba:return Math.floor((s+9)/10)*Math.floor((e+9)/10)*16;case wa:return Math.floor((s+11)/12)*Math.floor((e+9)/10)*16;case Sa:return Math.floor((s+11)/12)*Math.floor((e+11)/12)*16;case Ar:case Ta:case Ea:return Math.ceil(s/4)*Math.ceil(e/4)*16;case Th:case Aa:return Math.ceil(s/4)*Math.ceil(e/4)*8;case Ca:case Pa:return Math.ceil(s/4)*Math.ceil(e/4)*16}throw new Error(`Unable to determine texture byte length for ${t} format.`)}function Eg(s){switch(s){case Vn:case vh:return{byteLength:1,components:1};case Ds:case xh:case bn:return{byteLength:2,components:1};case Xa:case Ya:return{byteLength:2,components:4};case gi:case Wa:case Tn:return{byteLength:4,components:1};case _h:return{byteLength:4,components:3}}throw new Error(`Unknown texture type ${s}.`)}function Ag(s,e,t,n,i,r,o){const a=e.has("WEBGL_multisampled_render_to_texture")?e.get("WEBGL_multisampled_render_to_texture"):null,l=typeof navigator>"u"?!1:/OculusBrowser/g.test(navigator.userAgent),c=new Q,h=new WeakMap;let u;const d=new WeakMap;let f=!1;try{f=typeof OffscreenCanvas<"u"&&new OffscreenCanvas(1,1).getContext("2d")!==null}catch{}function g(F,A){return f?new OffscreenCanvas(F,A):Or("canvas")}function x(F,A,j){let ne=1;const re=pe(F);if((re.width>j||re.height>j)&&(ne=j/Math.max(re.width,re.height)),ne<1)if(typeof HTMLImageElement<"u"&&F instanceof HTMLImageElement||typeof HTMLCanvasElement<"u"&&F instanceof HTMLCanvasElement||typeof ImageBitmap<"u"&&F instanceof ImageBitmap||typeof VideoFrame<"u"&&F instanceof VideoFrame){const ie=Math.floor(ne*re.width),Pe=Math.floor(ne*re.height);u===void 0&&(u=g(ie,Pe));const me=A?g(ie,Pe):u;return me.width=ie,me.height=Pe,me.getContext("2d").drawImage(F,0,0,ie,Pe),console.warn("THREE.WebGLRenderer: Texture has been resized from ("+re.width+"x"+re.height+") to ("+ie+"x"+Pe+")."),me}else return"data"in F&&console.warn("THREE.WebGLRenderer: Image in DataTexture is too big ("+re.width+"x"+re.height+")."),F;return F}function p(F){return F.generateMipmaps&&F.minFilter!==$t&&F.minFilter!==Ct}function m(F){s.generateMipmap(F)}function _(F,A,j,ne,re=!1){if(F!==null){if(s[F]!==void 0)return s[F];console.warn("THREE.WebGLRenderer: Attempt to use non-existing WebGL internal format '"+F+"'")}let ie=A;if(A===s.RED&&(j===s.FLOAT&&(ie=s.R32F),j===s.HALF_FLOAT&&(ie=s.R16F),j===s.UNSIGNED_BYTE&&(ie=s.R8)),A===s.RED_INTEGER&&(j===s.UNSIGNED_BYTE&&(ie=s.R8UI),j===s.UNSIGNED_SHORT&&(ie=s.R16UI),j===s.UNSIGNED_INT&&(ie=s.R32UI),j===s.BYTE&&(ie=s.R8I),j===s.SHORT&&(ie=s.R16I),j===s.INT&&(ie=s.R32I)),A===s.RG&&(j===s.FLOAT&&(ie=s.RG32F),j===s.HALF_FLOAT&&(ie=s.RG16F),j===s.UNSIGNED_BYTE&&(ie=s.RG8)),A===s.RG_INTEGER&&(j===s.UNSIGNED_BYTE&&(ie=s.RG8UI),j===s.UNSIGNED_SHORT&&(ie=s.RG16UI),j===s.UNSIGNED_INT&&(ie=s.RG32UI),j===s.BYTE&&(ie=s.RG8I),j===s.SHORT&&(ie=s.RG16I),j===s.INT&&(ie=s.RG32I)),A===s.RGB_INTEGER&&(j===s.UNSIGNED_BYTE&&(ie=s.RGB8UI),j===s.UNSIGNED_SHORT&&(ie=s.RGB16UI),j===s.UNSIGNED_INT&&(ie=s.RGB32UI),j===s.BYTE&&(ie=s.RGB8I),j===s.SHORT&&(ie=s.RGB16I),j===s.INT&&(ie=s.RGB32I)),A===s.RGBA_INTEGER&&(j===s.UNSIGNED_BYTE&&(ie=s.RGBA8UI),j===s.UNSIGNED_SHORT&&(ie=s.RGBA16UI),j===s.UNSIGNED_INT&&(ie=s.RGBA32UI),j===s.BYTE&&(ie=s.RGBA8I),j===s.SHORT&&(ie=s.RGBA16I),j===s.INT&&(ie=s.RGBA32I)),A===s.RGB&&j===s.UNSIGNED_INT_5_9_9_9_REV&&(ie=s.RGB9_E5),A===s.RGBA){const Pe=re?Ir:nt.getTransfer(ne);j===s.FLOAT&&(ie=s.RGBA32F),j===s.HALF_FLOAT&&(ie=s.RGBA16F),j===s.UNSIGNED_BYTE&&(ie=Pe===ut?s.SRGB8_ALPHA8:s.RGBA8),j===s.UNSIGNED_SHORT_4_4_4_4&&(ie=s.RGBA4),j===s.UNSIGNED_SHORT_5_5_5_1&&(ie=s.RGB5_A1)}return(ie===s.R16F||ie===s.R32F||ie===s.RG16F||ie===s.RG32F||ie===s.RGBA16F||ie===s.RGBA32F)&&e.get("EXT_color_buffer_float"),ie}function v(F,A){let j;return F?A===null||A===gi||A===es?j=s.DEPTH24_STENCIL8:A===Tn?j=s.DEPTH32F_STENCIL8:A===Ds&&(j=s.DEPTH24_STENCIL8,console.warn("DepthTexture: 16 bit depth attachment is not supported with stencil. Using 24-bit attachment.")):A===null||A===gi||A===es?j=s.DEPTH_COMPONENT24:A===Tn?j=s.DEPTH_COMPONENT32F:A===Ds&&(j=s.DEPTH_COMPONENT16),j}function M(F,A){return p(F)===!0||F.isFramebufferTexture&&F.minFilter!==$t&&F.minFilter!==Ct?Math.log2(Math.max(A.width,A.height))+1:F.mipmaps!==void 0&&F.mipmaps.length>0?F.mipmaps.length:F.isCompressedTexture&&Array.isArray(F.image)?A.mipmaps.length:1}function S(F){const A=F.target;A.removeEventListener("dispose",S),C(A),A.isVideoTexture&&h.delete(A)}function E(F){const A=F.target;A.removeEventListener("dispose",E),T(A)}function C(F){const A=n.get(F);if(A.__webglInit===void 0)return;const j=F.source,ne=d.get(j);if(ne){const re=ne[A.__cacheKey];re.usedTimes--,re.usedTimes===0&&z(F),Object.keys(ne).length===0&&d.delete(j)}n.remove(F)}function z(F){const A=n.get(F);s.deleteTexture(A.__webglTexture);const j=F.source,ne=d.get(j);delete ne[A.__cacheKey],o.memory.textures--}function T(F){const A=n.get(F);if(F.depthTexture&&F.depthTexture.dispose(),F.isWebGLCubeRenderTarget)for(let ne=0;ne<6;ne++){if(Array.isArray(A.__webglFramebuffer[ne]))for(let re=0;re<A.__webglFramebuffer[ne].length;re++)s.deleteFramebuffer(A.__webglFramebuffer[ne][re]);else s.deleteFramebuffer(A.__webglFramebuffer[ne]);A.__webglDepthbuffer&&s.deleteRenderbuffer(A.__webglDepthbuffer[ne])}else{if(Array.isArray(A.__webglFramebuffer))for(let ne=0;ne<A.__webglFramebuffer.length;ne++)s.deleteFramebuffer(A.__webglFramebuffer[ne]);else s.deleteFramebuffer(A.__webglFramebuffer);if(A.__webglDepthbuffer&&s.deleteRenderbuffer(A.__webglDepthbuffer),A.__webglMultisampledFramebuffer&&s.deleteFramebuffer(A.__webglMultisampledFramebuffer),A.__webglColorRenderbuffer)for(let ne=0;ne<A.__webglColorRenderbuffer.length;ne++)A.__webglColorRenderbuffer[ne]&&s.deleteRenderbuffer(A.__webglColorRenderbuffer[ne]);A.__webglDepthRenderbuffer&&s.deleteRenderbuffer(A.__webglDepthRenderbuffer)}const j=F.textures;for(let ne=0,re=j.length;ne<re;ne++){const ie=n.get(j[ne]);ie.__webglTexture&&(s.deleteTexture(ie.__webglTexture),o.memory.textures--),n.remove(j[ne])}n.remove(F)}let y=0;function b(){y=0}function D(){const F=y;return F>=i.maxTextures&&console.warn("THREE.WebGLTextures: Trying to use "+F+" texture units while this GPU supports only "+i.maxTextures),y+=1,F}function L(F){const A=[];return A.push(F.wrapS),A.push(F.wrapT),A.push(F.wrapR||0),A.push(F.magFilter),A.push(F.minFilter),A.push(F.anisotropy),A.push(F.internalFormat),A.push(F.format),A.push(F.type),A.push(F.generateMipmaps),A.push(F.premultiplyAlpha),A.push(F.flipY),A.push(F.unpackAlignment),A.push(F.colorSpace),A.join()}function N(F,A){const j=n.get(F);if(F.isVideoTexture&&de(F),F.isRenderTargetTexture===!1&&F.version>0&&j.__version!==F.version){const ne=F.image;if(ne===null)console.warn("THREE.WebGLRenderer: Texture marked for update but no image data found.");else if(ne.complete===!1)console.warn("THREE.WebGLRenderer: Texture marked for update but image is incomplete");else{Z(j,F,A);return}}t.bindTexture(s.TEXTURE_2D,j.__webglTexture,s.TEXTURE0+A)}function B(F,A){const j=n.get(F);if(F.version>0&&j.__version!==F.version){Z(j,F,A);return}t.bindTexture(s.TEXTURE_2D_ARRAY,j.__webglTexture,s.TEXTURE0+A)}function k(F,A){const j=n.get(F);if(F.version>0&&j.__version!==F.version){Z(j,F,A);return}t.bindTexture(s.TEXTURE_3D,j.__webglTexture,s.TEXTURE0+A)}function q(F,A){const j=n.get(F);if(F.version>0&&j.__version!==F.version){W(j,F,A);return}t.bindTexture(s.TEXTURE_CUBE_MAP,j.__webglTexture,s.TEXTURE0+A)}const U={[na]:s.REPEAT,[fi]:s.CLAMP_TO_EDGE,[ia]:s.MIRRORED_REPEAT},V={[$t]:s.NEAREST,[ju]:s.NEAREST_MIPMAP_NEAREST,[Hs]:s.NEAREST_MIPMAP_LINEAR,[Ct]:s.LINEAR,[so]:s.LINEAR_MIPMAP_NEAREST,[pi]:s.LINEAR_MIPMAP_LINEAR},P={[$u]:s.NEVER,[sd]:s.ALWAYS,[Qu]:s.LESS,[Ah]:s.LEQUAL,[ed]:s.EQUAL,[id]:s.GEQUAL,[td]:s.GREATER,[nd]:s.NOTEQUAL};function O(F,A){if(A.type===Tn&&e.has("OES_texture_float_linear")===!1&&(A.magFilter===Ct||A.magFilter===so||A.magFilter===Hs||A.magFilter===pi||A.minFilter===Ct||A.minFilter===so||A.minFilter===Hs||A.minFilter===pi)&&console.warn("THREE.WebGLRenderer: Unable to use linear filtering with floating point textures. OES_texture_float_linear not supported on this device."),s.texParameteri(F,s.TEXTURE_WRAP_S,U[A.wrapS]),s.texParameteri(F,s.TEXTURE_WRAP_T,U[A.wrapT]),(F===s.TEXTURE_3D||F===s.TEXTURE_2D_ARRAY)&&s.texParameteri(F,s.TEXTURE_WRAP_R,U[A.wrapR]),s.texParameteri(F,s.TEXTURE_MAG_FILTER,V[A.magFilter]),s.texParameteri(F,s.TEXTURE_MIN_FILTER,V[A.minFilter]),A.compareFunction&&(s.texParameteri(F,s.TEXTURE_COMPARE_MODE,s.COMPARE_REF_TO_TEXTURE),s.texParameteri(F,s.TEXTURE_COMPARE_FUNC,P[A.compareFunction])),e.has("EXT_texture_filter_anisotropic")===!0){if(A.magFilter===$t||A.minFilter!==Hs&&A.minFilter!==pi||A.type===Tn&&e.has("OES_texture_float_linear")===!1)return;if(A.anisotropy>1||n.get(A).__currentAnisotropy){const j=e.get("EXT_texture_filter_anisotropic");s.texParameterf(F,j.TEXTURE_MAX_ANISOTROPY_EXT,Math.min(A.anisotropy,i.getMaxAnisotropy())),n.get(A).__currentAnisotropy=A.anisotropy}}}function H(F,A){let j=!1;F.__webglInit===void 0&&(F.__webglInit=!0,A.addEventListener("dispose",S));const ne=A.source;let re=d.get(ne);re===void 0&&(re={},d.set(ne,re));const ie=L(A);if(ie!==F.__cacheKey){re[ie]===void 0&&(re[ie]={texture:s.createTexture(),usedTimes:0},o.memory.textures++,j=!0),re[ie].usedTimes++;const Pe=re[F.__cacheKey];Pe!==void 0&&(re[F.__cacheKey].usedTimes--,Pe.usedTimes===0&&z(A)),F.__cacheKey=ie,F.__webglTexture=re[ie].texture}return j}function Z(F,A,j){let ne=s.TEXTURE_2D;(A.isDataArrayTexture||A.isCompressedArrayTexture)&&(ne=s.TEXTURE_2D_ARRAY),A.isData3DTexture&&(ne=s.TEXTURE_3D);const re=H(F,A),ie=A.source;t.bindTexture(ne,F.__webglTexture,s.TEXTURE0+j);const Pe=n.get(ie);if(ie.version!==Pe.__version||re===!0){t.activeTexture(s.TEXTURE0+j);const me=nt.getPrimaries(nt.workingColorSpace),we=A.colorSpace===$n?null:nt.getPrimaries(A.colorSpace),Ze=A.colorSpace===$n||me===we?s.NONE:s.BROWSER_DEFAULT_WEBGL;s.pixelStorei(s.UNPACK_FLIP_Y_WEBGL,A.flipY),s.pixelStorei(s.UNPACK_PREMULTIPLY_ALPHA_WEBGL,A.premultiplyAlpha),s.pixelStorei(s.UNPACK_ALIGNMENT,A.unpackAlignment),s.pixelStorei(s.UNPACK_COLORSPACE_CONVERSION_WEBGL,Ze);let ue=x(A.image,!1,i.maxTextureSize);ue=xe(A,ue);const Se=r.convert(A.format,A.colorSpace),Ve=r.convert(A.type);let He=_(A.internalFormat,Se,Ve,A.colorSpace,A.isVideoTexture);O(ne,A);let Te;const Je=A.mipmaps,We=A.isVideoTexture!==!0,ht=Pe.__version===void 0||re===!0,G=ie.dataReady,Me=M(A,ue);if(A.isDepthTexture)He=v(A.format===ts,A.type),ht&&(We?t.texStorage2D(s.TEXTURE_2D,1,He,ue.width,ue.height):t.texImage2D(s.TEXTURE_2D,0,He,ue.width,ue.height,0,Se,Ve,null));else if(A.isDataTexture)if(Je.length>0){We&&ht&&t.texStorage2D(s.TEXTURE_2D,Me,He,Je[0].width,Je[0].height);for(let ee=0,oe=Je.length;ee<oe;ee++)Te=Je[ee],We?G&&t.texSubImage2D(s.TEXTURE_2D,ee,0,0,Te.width,Te.height,Se,Ve,Te.data):t.texImage2D(s.TEXTURE_2D,ee,He,Te.width,Te.height,0,Se,Ve,Te.data);A.generateMipmaps=!1}else We?(ht&&t.texStorage2D(s.TEXTURE_2D,Me,He,ue.width,ue.height),G&&t.texSubImage2D(s.TEXTURE_2D,0,0,0,ue.width,ue.height,Se,Ve,ue.data)):t.texImage2D(s.TEXTURE_2D,0,He,ue.width,ue.height,0,Se,Ve,ue.data);else if(A.isCompressedTexture)if(A.isCompressedArrayTexture){We&&ht&&t.texStorage3D(s.TEXTURE_2D_ARRAY,Me,He,Je[0].width,Je[0].height,ue.depth);for(let ee=0,oe=Je.length;ee<oe;ee++)if(Te=Je[ee],A.format!==sn)if(Se!==null)if(We){if(G)if(A.layerUpdates.size>0){const _e=gc(Te.width,Te.height,A.format,A.type);for(const be of A.layerUpdates){const Qe=Te.data.subarray(be*_e/Te.data.BYTES_PER_ELEMENT,(be+1)*_e/Te.data.BYTES_PER_ELEMENT);t.compressedTexSubImage3D(s.TEXTURE_2D_ARRAY,ee,0,0,be,Te.width,Te.height,1,Se,Qe,0,0)}A.clearLayerUpdates()}else t.compressedTexSubImage3D(s.TEXTURE_2D_ARRAY,ee,0,0,0,Te.width,Te.height,ue.depth,Se,Te.data,0,0)}else t.compressedTexImage3D(s.TEXTURE_2D_ARRAY,ee,He,Te.width,Te.height,ue.depth,0,Te.data,0,0);else console.warn("THREE.WebGLRenderer: Attempt to load unsupported compressed texture format in .uploadTexture()");else We?G&&t.texSubImage3D(s.TEXTURE_2D_ARRAY,ee,0,0,0,Te.width,Te.height,ue.depth,Se,Ve,Te.data):t.texImage3D(s.TEXTURE_2D_ARRAY,ee,He,Te.width,Te.height,ue.depth,0,Se,Ve,Te.data)}else{We&&ht&&t.texStorage2D(s.TEXTURE_2D,Me,He,Je[0].width,Je[0].height);for(let ee=0,oe=Je.length;ee<oe;ee++)Te=Je[ee],A.format!==sn?Se!==null?We?G&&t.compressedTexSubImage2D(s.TEXTURE_2D,ee,0,0,Te.width,Te.height,Se,Te.data):t.compressedTexImage2D(s.TEXTURE_2D,ee,He,Te.width,Te.height,0,Te.data):console.warn("THREE.WebGLRenderer: Attempt to load unsupported compressed texture format in .uploadTexture()"):We?G&&t.texSubImage2D(s.TEXTURE_2D,ee,0,0,Te.width,Te.height,Se,Ve,Te.data):t.texImage2D(s.TEXTURE_2D,ee,He,Te.width,Te.height,0,Se,Ve,Te.data)}else if(A.isDataArrayTexture)if(We){if(ht&&t.texStorage3D(s.TEXTURE_2D_ARRAY,Me,He,ue.width,ue.height,ue.depth),G)if(A.layerUpdates.size>0){const ee=gc(ue.width,ue.height,A.format,A.type);for(const oe of A.layerUpdates){const _e=ue.data.subarray(oe*ee/ue.data.BYTES_PER_ELEMENT,(oe+1)*ee/ue.data.BYTES_PER_ELEMENT);t.texSubImage3D(s.TEXTURE_2D_ARRAY,0,0,0,oe,ue.width,ue.height,1,Se,Ve,_e)}A.clearLayerUpdates()}else t.texSubImage3D(s.TEXTURE_2D_ARRAY,0,0,0,0,ue.width,ue.height,ue.depth,Se,Ve,ue.data)}else t.texImage3D(s.TEXTURE_2D_ARRAY,0,He,ue.width,ue.height,ue.depth,0,Se,Ve,ue.data);else if(A.isData3DTexture)We?(ht&&t.texStorage3D(s.TEXTURE_3D,Me,He,ue.width,ue.height,ue.depth),G&&t.texSubImage3D(s.TEXTURE_3D,0,0,0,0,ue.width,ue.height,ue.depth,Se,Ve,ue.data)):t.texImage3D(s.TEXTURE_3D,0,He,ue.width,ue.height,ue.depth,0,Se,Ve,ue.data);else if(A.isFramebufferTexture){if(ht)if(We)t.texStorage2D(s.TEXTURE_2D,Me,He,ue.width,ue.height);else{let ee=ue.width,oe=ue.height;for(let _e=0;_e<Me;_e++)t.texImage2D(s.TEXTURE_2D,_e,He,ee,oe,0,Se,Ve,null),ee>>=1,oe>>=1}}else if(Je.length>0){if(We&&ht){const ee=pe(Je[0]);t.texStorage2D(s.TEXTURE_2D,Me,He,ee.width,ee.height)}for(let ee=0,oe=Je.length;ee<oe;ee++)Te=Je[ee],We?G&&t.texSubImage2D(s.TEXTURE_2D,ee,0,0,Se,Ve,Te):t.texImage2D(s.TEXTURE_2D,ee,He,Se,Ve,Te);A.generateMipmaps=!1}else if(We){if(ht){const ee=pe(ue);t.texStorage2D(s.TEXTURE_2D,Me,He,ee.width,ee.height)}G&&t.texSubImage2D(s.TEXTURE_2D,0,0,0,Se,Ve,ue)}else t.texImage2D(s.TEXTURE_2D,0,He,Se,Ve,ue);p(A)&&m(ne),Pe.__version=ie.version,A.onUpdate&&A.onUpdate(A)}F.__version=A.version}function W(F,A,j){if(A.image.length!==6)return;const ne=H(F,A),re=A.source;t.bindTexture(s.TEXTURE_CUBE_MAP,F.__webglTexture,s.TEXTURE0+j);const ie=n.get(re);if(re.version!==ie.__version||ne===!0){t.activeTexture(s.TEXTURE0+j);const Pe=nt.getPrimaries(nt.workingColorSpace),me=A.colorSpace===$n?null:nt.getPrimaries(A.colorSpace),we=A.colorSpace===$n||Pe===me?s.NONE:s.BROWSER_DEFAULT_WEBGL;s.pixelStorei(s.UNPACK_FLIP_Y_WEBGL,A.flipY),s.pixelStorei(s.UNPACK_PREMULTIPLY_ALPHA_WEBGL,A.premultiplyAlpha),s.pixelStorei(s.UNPACK_ALIGNMENT,A.unpackAlignment),s.pixelStorei(s.UNPACK_COLORSPACE_CONVERSION_WEBGL,we);const Ze=A.isCompressedTexture||A.image[0].isCompressedTexture,ue=A.image[0]&&A.image[0].isDataTexture,Se=[];for(let oe=0;oe<6;oe++)!Ze&&!ue?Se[oe]=x(A.image[oe],!0,i.maxCubemapSize):Se[oe]=ue?A.image[oe].image:A.image[oe],Se[oe]=xe(A,Se[oe]);const Ve=Se[0],He=r.convert(A.format,A.colorSpace),Te=r.convert(A.type),Je=_(A.internalFormat,He,Te,A.colorSpace),We=A.isVideoTexture!==!0,ht=ie.__version===void 0||ne===!0,G=re.dataReady;let Me=M(A,Ve);O(s.TEXTURE_CUBE_MAP,A);let ee;if(Ze){We&&ht&&t.texStorage2D(s.TEXTURE_CUBE_MAP,Me,Je,Ve.width,Ve.height);for(let oe=0;oe<6;oe++){ee=Se[oe].mipmaps;for(let _e=0;_e<ee.length;_e++){const be=ee[_e];A.format!==sn?He!==null?We?G&&t.compressedTexSubImage2D(s.TEXTURE_CUBE_MAP_POSITIVE_X+oe,_e,0,0,be.width,be.height,He,be.data):t.compressedTexImage2D(s.TEXTURE_CUBE_MAP_POSITIVE_X+oe,_e,Je,be.width,be.height,0,be.data):console.warn("THREE.WebGLRenderer: Attempt to load unsupported compressed texture format in .setTextureCube()"):We?G&&t.texSubImage2D(s.TEXTURE_CUBE_MAP_POSITIVE_X+oe,_e,0,0,be.width,be.height,He,Te,be.data):t.texImage2D(s.TEXTURE_CUBE_MAP_POSITIVE_X+oe,_e,Je,be.width,be.height,0,He,Te,be.data)}}}else{if(ee=A.mipmaps,We&&ht){ee.length>0&&Me++;const oe=pe(Se[0]);t.texStorage2D(s.TEXTURE_CUBE_MAP,Me,Je,oe.width,oe.height)}for(let oe=0;oe<6;oe++)if(ue){We?G&&t.texSubImage2D(s.TEXTURE_CUBE_MAP_POSITIVE_X+oe,0,0,0,Se[oe].width,Se[oe].height,He,Te,Se[oe].data):t.texImage2D(s.TEXTURE_CUBE_MAP_POSITIVE_X+oe,0,Je,Se[oe].width,Se[oe].height,0,He,Te,Se[oe].data);for(let _e=0;_e<ee.length;_e++){const Qe=ee[_e].image[oe].image;We?G&&t.texSubImage2D(s.TEXTURE_CUBE_MAP_POSITIVE_X+oe,_e+1,0,0,Qe.width,Qe.height,He,Te,Qe.data):t.texImage2D(s.TEXTURE_CUBE_MAP_POSITIVE_X+oe,_e+1,Je,Qe.width,Qe.height,0,He,Te,Qe.data)}}else{We?G&&t.texSubImage2D(s.TEXTURE_CUBE_MAP_POSITIVE_X+oe,0,0,0,He,Te,Se[oe]):t.texImage2D(s.TEXTURE_CUBE_MAP_POSITIVE_X+oe,0,Je,He,Te,Se[oe]);for(let _e=0;_e<ee.length;_e++){const be=ee[_e];We?G&&t.texSubImage2D(s.TEXTURE_CUBE_MAP_POSITIVE_X+oe,_e+1,0,0,He,Te,be.image[oe]):t.texImage2D(s.TEXTURE_CUBE_MAP_POSITIVE_X+oe,_e+1,Je,He,Te,be.image[oe])}}}p(A)&&m(s.TEXTURE_CUBE_MAP),ie.__version=re.version,A.onUpdate&&A.onUpdate(A)}F.__version=A.version}function $(F,A,j,ne,re,ie){const Pe=r.convert(j.format,j.colorSpace),me=r.convert(j.type),we=_(j.internalFormat,Pe,me,j.colorSpace);if(!n.get(A).__hasExternalTextures){const ue=Math.max(1,A.width>>ie),Se=Math.max(1,A.height>>ie);re===s.TEXTURE_3D||re===s.TEXTURE_2D_ARRAY?t.texImage3D(re,ie,we,ue,Se,A.depth,0,Pe,me,null):t.texImage2D(re,ie,we,ue,Se,0,Pe,me,null)}t.bindFramebuffer(s.FRAMEBUFFER,F),se(A)?a.framebufferTexture2DMultisampleEXT(s.FRAMEBUFFER,ne,re,n.get(j).__webglTexture,0,ae(A)):(re===s.TEXTURE_2D||re>=s.TEXTURE_CUBE_MAP_POSITIVE_X&&re<=s.TEXTURE_CUBE_MAP_NEGATIVE_Z)&&s.framebufferTexture2D(s.FRAMEBUFFER,ne,re,n.get(j).__webglTexture,ie),t.bindFramebuffer(s.FRAMEBUFFER,null)}function le(F,A,j){if(s.bindRenderbuffer(s.RENDERBUFFER,F),A.depthBuffer){const ne=A.depthTexture,re=ne&&ne.isDepthTexture?ne.type:null,ie=v(A.stencilBuffer,re),Pe=A.stencilBuffer?s.DEPTH_STENCIL_ATTACHMENT:s.DEPTH_ATTACHMENT,me=ae(A);se(A)?a.renderbufferStorageMultisampleEXT(s.RENDERBUFFER,me,ie,A.width,A.height):j?s.renderbufferStorageMultisample(s.RENDERBUFFER,me,ie,A.width,A.height):s.renderbufferStorage(s.RENDERBUFFER,ie,A.width,A.height),s.framebufferRenderbuffer(s.FRAMEBUFFER,Pe,s.RENDERBUFFER,F)}else{const ne=A.textures;for(let re=0;re<ne.length;re++){const ie=ne[re],Pe=r.convert(ie.format,ie.colorSpace),me=r.convert(ie.type),we=_(ie.internalFormat,Pe,me,ie.colorSpace),Ze=ae(A);j&&se(A)===!1?s.renderbufferStorageMultisample(s.RENDERBUFFER,Ze,we,A.width,A.height):se(A)?a.renderbufferStorageMultisampleEXT(s.RENDERBUFFER,Ze,we,A.width,A.height):s.renderbufferStorage(s.RENDERBUFFER,we,A.width,A.height)}}s.bindRenderbuffer(s.RENDERBUFFER,null)}function he(F,A){if(A&&A.isWebGLCubeRenderTarget)throw new Error("Depth Texture with cube render targets is not supported");if(t.bindFramebuffer(s.FRAMEBUFFER,F),!(A.depthTexture&&A.depthTexture.isDepthTexture))throw new Error("renderTarget.depthTexture must be an instance of THREE.DepthTexture");(!n.get(A.depthTexture).__webglTexture||A.depthTexture.image.width!==A.width||A.depthTexture.image.height!==A.height)&&(A.depthTexture.image.width=A.width,A.depthTexture.image.height=A.height,A.depthTexture.needsUpdate=!0),N(A.depthTexture,0);const ne=n.get(A.depthTexture).__webglTexture,re=ae(A);if(A.depthTexture.format===ji)se(A)?a.framebufferTexture2DMultisampleEXT(s.FRAMEBUFFER,s.DEPTH_ATTACHMENT,s.TEXTURE_2D,ne,0,re):s.framebufferTexture2D(s.FRAMEBUFFER,s.DEPTH_ATTACHMENT,s.TEXTURE_2D,ne,0);else if(A.depthTexture.format===ts)se(A)?a.framebufferTexture2DMultisampleEXT(s.FRAMEBUFFER,s.DEPTH_STENCIL_ATTACHMENT,s.TEXTURE_2D,ne,0,re):s.framebufferTexture2D(s.FRAMEBUFFER,s.DEPTH_STENCIL_ATTACHMENT,s.TEXTURE_2D,ne,0);else throw new Error("Unknown depthTexture format")}function Ce(F){const A=n.get(F),j=F.isWebGLCubeRenderTarget===!0;if(A.__boundDepthTexture!==F.depthTexture){const ne=F.depthTexture;if(A.__depthDisposeCallback&&A.__depthDisposeCallback(),ne){const re=()=>{delete A.__boundDepthTexture,delete A.__depthDisposeCallback,ne.removeEventListener("dispose",re)};ne.addEventListener("dispose",re),A.__depthDisposeCallback=re}A.__boundDepthTexture=ne}if(F.depthTexture&&!A.__autoAllocateDepthBuffer){if(j)throw new Error("target.depthTexture not supported in Cube render targets");he(A.__webglFramebuffer,F)}else if(j){A.__webglDepthbuffer=[];for(let ne=0;ne<6;ne++)if(t.bindFramebuffer(s.FRAMEBUFFER,A.__webglFramebuffer[ne]),A.__webglDepthbuffer[ne]===void 0)A.__webglDepthbuffer[ne]=s.createRenderbuffer(),le(A.__webglDepthbuffer[ne],F,!1);else{const re=F.stencilBuffer?s.DEPTH_STENCIL_ATTACHMENT:s.DEPTH_ATTACHMENT,ie=A.__webglDepthbuffer[ne];s.bindRenderbuffer(s.RENDERBUFFER,ie),s.framebufferRenderbuffer(s.FRAMEBUFFER,re,s.RENDERBUFFER,ie)}}else if(t.bindFramebuffer(s.FRAMEBUFFER,A.__webglFramebuffer),A.__webglDepthbuffer===void 0)A.__webglDepthbuffer=s.createRenderbuffer(),le(A.__webglDepthbuffer,F,!1);else{const ne=F.stencilBuffer?s.DEPTH_STENCIL_ATTACHMENT:s.DEPTH_ATTACHMENT,re=A.__webglDepthbuffer;s.bindRenderbuffer(s.RENDERBUFFER,re),s.framebufferRenderbuffer(s.FRAMEBUFFER,ne,s.RENDERBUFFER,re)}t.bindFramebuffer(s.FRAMEBUFFER,null)}function Oe(F,A,j){const ne=n.get(F);A!==void 0&&$(ne.__webglFramebuffer,F,F.texture,s.COLOR_ATTACHMENT0,s.TEXTURE_2D,0),j!==void 0&&Ce(F)}function Ie(F){const A=F.texture,j=n.get(F),ne=n.get(A);F.addEventListener("dispose",E);const re=F.textures,ie=F.isWebGLCubeRenderTarget===!0,Pe=re.length>1;if(Pe||(ne.__webglTexture===void 0&&(ne.__webglTexture=s.createTexture()),ne.__version=A.version,o.memory.textures++),ie){j.__webglFramebuffer=[];for(let me=0;me<6;me++)if(A.mipmaps&&A.mipmaps.length>0){j.__webglFramebuffer[me]=[];for(let we=0;we<A.mipmaps.length;we++)j.__webglFramebuffer[me][we]=s.createFramebuffer()}else j.__webglFramebuffer[me]=s.createFramebuffer()}else{if(A.mipmaps&&A.mipmaps.length>0){j.__webglFramebuffer=[];for(let me=0;me<A.mipmaps.length;me++)j.__webglFramebuffer[me]=s.createFramebuffer()}else j.__webglFramebuffer=s.createFramebuffer();if(Pe)for(let me=0,we=re.length;me<we;me++){const Ze=n.get(re[me]);Ze.__webglTexture===void 0&&(Ze.__webglTexture=s.createTexture(),o.memory.textures++)}if(F.samples>0&&se(F)===!1){j.__webglMultisampledFramebuffer=s.createFramebuffer(),j.__webglColorRenderbuffer=[],t.bindFramebuffer(s.FRAMEBUFFER,j.__webglMultisampledFramebuffer);for(let me=0;me<re.length;me++){const we=re[me];j.__webglColorRenderbuffer[me]=s.createRenderbuffer(),s.bindRenderbuffer(s.RENDERBUFFER,j.__webglColorRenderbuffer[me]);const Ze=r.convert(we.format,we.colorSpace),ue=r.convert(we.type),Se=_(we.internalFormat,Ze,ue,we.colorSpace,F.isXRRenderTarget===!0),Ve=ae(F);s.renderbufferStorageMultisample(s.RENDERBUFFER,Ve,Se,F.width,F.height),s.framebufferRenderbuffer(s.FRAMEBUFFER,s.COLOR_ATTACHMENT0+me,s.RENDERBUFFER,j.__webglColorRenderbuffer[me])}s.bindRenderbuffer(s.RENDERBUFFER,null),F.depthBuffer&&(j.__webglDepthRenderbuffer=s.createRenderbuffer(),le(j.__webglDepthRenderbuffer,F,!0)),t.bindFramebuffer(s.FRAMEBUFFER,null)}}if(ie){t.bindTexture(s.TEXTURE_CUBE_MAP,ne.__webglTexture),O(s.TEXTURE_CUBE_MAP,A);for(let me=0;me<6;me++)if(A.mipmaps&&A.mipmaps.length>0)for(let we=0;we<A.mipmaps.length;we++)$(j.__webglFramebuffer[me][we],F,A,s.COLOR_ATTACHMENT0,s.TEXTURE_CUBE_MAP_POSITIVE_X+me,we);else $(j.__webglFramebuffer[me],F,A,s.COLOR_ATTACHMENT0,s.TEXTURE_CUBE_MAP_POSITIVE_X+me,0);p(A)&&m(s.TEXTURE_CUBE_MAP),t.unbindTexture()}else if(Pe){for(let me=0,we=re.length;me<we;me++){const Ze=re[me],ue=n.get(Ze);t.bindTexture(s.TEXTURE_2D,ue.__webglTexture),O(s.TEXTURE_2D,Ze),$(j.__webglFramebuffer,F,Ze,s.COLOR_ATTACHMENT0+me,s.TEXTURE_2D,0),p(Ze)&&m(s.TEXTURE_2D)}t.unbindTexture()}else{let me=s.TEXTURE_2D;if((F.isWebGL3DRenderTarget||F.isWebGLArrayRenderTarget)&&(me=F.isWebGL3DRenderTarget?s.TEXTURE_3D:s.TEXTURE_2D_ARRAY),t.bindTexture(me,ne.__webglTexture),O(me,A),A.mipmaps&&A.mipmaps.length>0)for(let we=0;we<A.mipmaps.length;we++)$(j.__webglFramebuffer[we],F,A,s.COLOR_ATTACHMENT0,me,we);else $(j.__webglFramebuffer,F,A,s.COLOR_ATTACHMENT0,me,0);p(A)&&m(me),t.unbindTexture()}F.depthBuffer&&Ce(F)}function ze(F){const A=F.textures;for(let j=0,ne=A.length;j<ne;j++){const re=A[j];if(p(re)){const ie=F.isWebGLCubeRenderTarget?s.TEXTURE_CUBE_MAP:s.TEXTURE_2D,Pe=n.get(re).__webglTexture;t.bindTexture(ie,Pe),m(ie),t.unbindTexture()}}}const te=[],I=[];function ce(F){if(F.samples>0){if(se(F)===!1){const A=F.textures,j=F.width,ne=F.height;let re=s.COLOR_BUFFER_BIT;const ie=F.stencilBuffer?s.DEPTH_STENCIL_ATTACHMENT:s.DEPTH_ATTACHMENT,Pe=n.get(F),me=A.length>1;if(me)for(let we=0;we<A.length;we++)t.bindFramebuffer(s.FRAMEBUFFER,Pe.__webglMultisampledFramebuffer),s.framebufferRenderbuffer(s.FRAMEBUFFER,s.COLOR_ATTACHMENT0+we,s.RENDERBUFFER,null),t.bindFramebuffer(s.FRAMEBUFFER,Pe.__webglFramebuffer),s.framebufferTexture2D(s.DRAW_FRAMEBUFFER,s.COLOR_ATTACHMENT0+we,s.TEXTURE_2D,null,0);t.bindFramebuffer(s.READ_FRAMEBUFFER,Pe.__webglMultisampledFramebuffer),t.bindFramebuffer(s.DRAW_FRAMEBUFFER,Pe.__webglFramebuffer);for(let we=0;we<A.length;we++){if(F.resolveDepthBuffer&&(F.depthBuffer&&(re|=s.DEPTH_BUFFER_BIT),F.stencilBuffer&&F.resolveStencilBuffer&&(re|=s.STENCIL_BUFFER_BIT)),me){s.framebufferRenderbuffer(s.READ_FRAMEBUFFER,s.COLOR_ATTACHMENT0,s.RENDERBUFFER,Pe.__webglColorRenderbuffer[we]);const Ze=n.get(A[we]).__webglTexture;s.framebufferTexture2D(s.DRAW_FRAMEBUFFER,s.COLOR_ATTACHMENT0,s.TEXTURE_2D,Ze,0)}s.blitFramebuffer(0,0,j,ne,0,0,j,ne,re,s.NEAREST),l===!0&&(te.length=0,I.length=0,te.push(s.COLOR_ATTACHMENT0+we),F.depthBuffer&&F.resolveDepthBuffer===!1&&(te.push(ie),I.push(ie),s.invalidateFramebuffer(s.DRAW_FRAMEBUFFER,I)),s.invalidateFramebuffer(s.READ_FRAMEBUFFER,te))}if(t.bindFramebuffer(s.READ_FRAMEBUFFER,null),t.bindFramebuffer(s.DRAW_FRAMEBUFFER,null),me)for(let we=0;we<A.length;we++){t.bindFramebuffer(s.FRAMEBUFFER,Pe.__webglMultisampledFramebuffer),s.framebufferRenderbuffer(s.FRAMEBUFFER,s.COLOR_ATTACHMENT0+we,s.RENDERBUFFER,Pe.__webglColorRenderbuffer[we]);const Ze=n.get(A[we]).__webglTexture;t.bindFramebuffer(s.FRAMEBUFFER,Pe.__webglFramebuffer),s.framebufferTexture2D(s.DRAW_FRAMEBUFFER,s.COLOR_ATTACHMENT0+we,s.TEXTURE_2D,Ze,0)}t.bindFramebuffer(s.DRAW_FRAMEBUFFER,Pe.__webglMultisampledFramebuffer)}else if(F.depthBuffer&&F.resolveDepthBuffer===!1&&l){const A=F.stencilBuffer?s.DEPTH_STENCIL_ATTACHMENT:s.DEPTH_ATTACHMENT;s.invalidateFramebuffer(s.DRAW_FRAMEBUFFER,[A])}}}function ae(F){return Math.min(i.maxSamples,F.samples)}function se(F){const A=n.get(F);return F.samples>0&&e.has("WEBGL_multisampled_render_to_texture")===!0&&A.__useRenderToTexture!==!1}function de(F){const A=o.render.frame;h.get(F)!==A&&(h.set(F,A),F.update())}function xe(F,A){const j=F.colorSpace,ne=F.format,re=F.type;return F.isCompressedTexture===!0||F.isVideoTexture===!0||j!==Hn&&j!==$n&&(nt.getTransfer(j)===ut?(ne!==sn||re!==Vn)&&console.warn("THREE.WebGLTextures: sRGB encoded textures have to use RGBAFormat and UnsignedByteType."):console.error("THREE.WebGLTextures: Unsupported texture color space:",j)),A}function pe(F){return typeof HTMLImageElement<"u"&&F instanceof HTMLImageElement?(c.width=F.naturalWidth||F.width,c.height=F.naturalHeight||F.height):typeof VideoFrame<"u"&&F instanceof VideoFrame?(c.width=F.displayWidth,c.height=F.displayHeight):(c.width=F.width,c.height=F.height),c}this.allocateTextureUnit=D,this.resetTextureUnits=b,this.setTexture2D=N,this.setTexture2DArray=B,this.setTexture3D=k,this.setTextureCube=q,this.rebindTextures=Oe,this.setupRenderTarget=Ie,this.updateRenderTargetMipmap=ze,this.updateMultisampleRenderTarget=ce,this.setupDepthRenderbuffer=Ce,this.setupFrameBufferTexture=$,this.useMultisampledRTT=se}function Cg(s,e){function t(n,i=$n){let r;const o=nt.getTransfer(i);if(n===Vn)return s.UNSIGNED_BYTE;if(n===Xa)return s.UNSIGNED_SHORT_4_4_4_4;if(n===Ya)return s.UNSIGNED_SHORT_5_5_5_1;if(n===_h)return s.UNSIGNED_INT_5_9_9_9_REV;if(n===vh)return s.BYTE;if(n===xh)return s.SHORT;if(n===Ds)return s.UNSIGNED_SHORT;if(n===Wa)return s.INT;if(n===gi)return s.UNSIGNED_INT;if(n===Tn)return s.FLOAT;if(n===bn)return s.HALF_FLOAT;if(n===yh)return s.ALPHA;if(n===Mh)return s.RGB;if(n===sn)return s.RGBA;if(n===bh)return s.LUMINANCE;if(n===wh)return s.LUMINANCE_ALPHA;if(n===ji)return s.DEPTH_COMPONENT;if(n===ts)return s.DEPTH_STENCIL;if(n===qa)return s.RED;if(n===ja)return s.RED_INTEGER;if(n===Sh)return s.RG;if(n===Ka)return s.RG_INTEGER;if(n===Za)return s.RGBA_INTEGER;if(n===wr||n===Sr||n===Tr||n===Er)if(o===ut)if(r=e.get("WEBGL_compressed_texture_s3tc_srgb"),r!==null){if(n===wr)return r.COMPRESSED_SRGB_S3TC_DXT1_EXT;if(n===Sr)return r.COMPRESSED_SRGB_ALPHA_S3TC_DXT1_EXT;if(n===Tr)return r.COMPRESSED_SRGB_ALPHA_S3TC_DXT3_EXT;if(n===Er)return r.COMPRESSED_SRGB_ALPHA_S3TC_DXT5_EXT}else return null;else if(r=e.get("WEBGL_compressed_texture_s3tc"),r!==null){if(n===wr)return r.COMPRESSED_RGB_S3TC_DXT1_EXT;if(n===Sr)return r.COMPRESSED_RGBA_S3TC_DXT1_EXT;if(n===Tr)return r.COMPRESSED_RGBA_S3TC_DXT3_EXT;if(n===Er)return r.COMPRESSED_RGBA_S3TC_DXT5_EXT}else return null;if(n===sa||n===ra||n===oa||n===aa)if(r=e.get("WEBGL_compressed_texture_pvrtc"),r!==null){if(n===sa)return r.COMPRESSED_RGB_PVRTC_4BPPV1_IMG;if(n===ra)return r.COMPRESSED_RGB_PVRTC_2BPPV1_IMG;if(n===oa)return r.COMPRESSED_RGBA_PVRTC_4BPPV1_IMG;if(n===aa)return r.COMPRESSED_RGBA_PVRTC_2BPPV1_IMG}else return null;if(n===la||n===ca||n===ha)if(r=e.get("WEBGL_compressed_texture_etc"),r!==null){if(n===la||n===ca)return o===ut?r.COMPRESSED_SRGB8_ETC2:r.COMPRESSED_RGB8_ETC2;if(n===ha)return o===ut?r.COMPRESSED_SRGB8_ALPHA8_ETC2_EAC:r.COMPRESSED_RGBA8_ETC2_EAC}else return null;if(n===ua||n===da||n===fa||n===pa||n===ma||n===ga||n===va||n===xa||n===_a||n===ya||n===Ma||n===ba||n===wa||n===Sa)if(r=e.get("WEBGL_compressed_texture_astc"),r!==null){if(n===ua)return o===ut?r.COMPRESSED_SRGB8_ALPHA8_ASTC_4x4_KHR:r.COMPRESSED_RGBA_ASTC_4x4_KHR;if(n===da)return o===ut?r.COMPRESSED_SRGB8_ALPHA8_ASTC_5x4_KHR:r.COMPRESSED_RGBA_ASTC_5x4_KHR;if(n===fa)return o===ut?r.COMPRESSED_SRGB8_ALPHA8_ASTC_5x5_KHR:r.COMPRESSED_RGBA_ASTC_5x5_KHR;if(n===pa)return o===ut?r.COMPRESSED_SRGB8_ALPHA8_ASTC_6x5_KHR:r.COMPRESSED_RGBA_ASTC_6x5_KHR;if(n===ma)return o===ut?r.COMPRESSED_SRGB8_ALPHA8_ASTC_6x6_KHR:r.COMPRESSED_RGBA_ASTC_6x6_KHR;if(n===ga)return o===ut?r.COMPRESSED_SRGB8_ALPHA8_ASTC_8x5_KHR:r.COMPRESSED_RGBA_ASTC_8x5_KHR;if(n===va)return o===ut?r.COMPRESSED_SRGB8_ALPHA8_ASTC_8x6_KHR:r.COMPRESSED_RGBA_ASTC_8x6_KHR;if(n===xa)return o===ut?r.COMPRESSED_SRGB8_ALPHA8_ASTC_8x8_KHR:r.COMPRESSED_RGBA_ASTC_8x8_KHR;if(n===_a)return o===ut?r.COMPRESSED_SRGB8_ALPHA8_ASTC_10x5_KHR:r.COMPRESSED_RGBA_ASTC_10x5_KHR;if(n===ya)return o===ut?r.COMPRESSED_SRGB8_ALPHA8_ASTC_10x6_KHR:r.COMPRESSED_RGBA_ASTC_10x6_KHR;if(n===Ma)return o===ut?r.COMPRESSED_SRGB8_ALPHA8_ASTC_10x8_KHR:r.COMPRESSED_RGBA_ASTC_10x8_KHR;if(n===ba)return o===ut?r.COMPRESSED_SRGB8_ALPHA8_ASTC_10x10_KHR:r.COMPRESSED_RGBA_ASTC_10x10_KHR;if(n===wa)return o===ut?r.COMPRESSED_SRGB8_ALPHA8_ASTC_12x10_KHR:r.COMPRESSED_RGBA_ASTC_12x10_KHR;if(n===Sa)return o===ut?r.COMPRESSED_SRGB8_ALPHA8_ASTC_12x12_KHR:r.COMPRESSED_RGBA_ASTC_12x12_KHR}else return null;if(n===Ar||n===Ta||n===Ea)if(r=e.get("EXT_texture_compression_bptc"),r!==null){if(n===Ar)return o===ut?r.COMPRESSED_SRGB_ALPHA_BPTC_UNORM_EXT:r.COMPRESSED_RGBA_BPTC_UNORM_EXT;if(n===Ta)return r.COMPRESSED_RGB_BPTC_SIGNED_FLOAT_EXT;if(n===Ea)return r.COMPRESSED_RGB_BPTC_UNSIGNED_FLOAT_EXT}else return null;if(n===Th||n===Aa||n===Ca||n===Pa)if(r=e.get("EXT_texture_compression_rgtc"),r!==null){if(n===Ar)return r.COMPRESSED_RED_RGTC1_EXT;if(n===Aa)return r.COMPRESSED_SIGNED_RED_RGTC1_EXT;if(n===Ca)return r.COMPRESSED_RED_GREEN_RGTC2_EXT;if(n===Pa)return r.COMPRESSED_SIGNED_RED_GREEN_RGTC2_EXT}else return null;return n===es?s.UNSIGNED_INT_24_8:s[n]!==void 0?s[n]:null}return{convert:t}}class Pg extends Jt{constructor(e=[]){super(),this.isArrayCamera=!0,this.cameras=e}}class qe extends Mt{constructor(){super(),this.isGroup=!0,this.type="Group"}}const Rg={type:"move"};class Lo{constructor(){this._targetRay=null,this._grip=null,this._hand=null}getHandSpace(){return this._hand===null&&(this._hand=new qe,this._hand.matrixAutoUpdate=!1,this._hand.visible=!1,this._hand.joints={},this._hand.inputState={pinching:!1}),this._hand}getTargetRaySpace(){return this._targetRay===null&&(this._targetRay=new qe,this._targetRay.matrixAutoUpdate=!1,this._targetRay.visible=!1,this._targetRay.hasLinearVelocity=!1,this._targetRay.linearVelocity=new w,this._targetRay.hasAngularVelocity=!1,this._targetRay.angularVelocity=new w),this._targetRay}getGripSpace(){return this._grip===null&&(this._grip=new qe,this._grip.matrixAutoUpdate=!1,this._grip.visible=!1,this._grip.hasLinearVelocity=!1,this._grip.linearVelocity=new w,this._grip.hasAngularVelocity=!1,this._grip.angularVelocity=new w),this._grip}dispatchEvent(e){return this._targetRay!==null&&this._targetRay.dispatchEvent(e),this._grip!==null&&this._grip.dispatchEvent(e),this._hand!==null&&this._hand.dispatchEvent(e),this}connect(e){if(e&&e.hand){const t=this._hand;if(t)for(const n of e.hand.values())this._getHandJoint(t,n)}return this.dispatchEvent({type:"connected",data:e}),this}disconnect(e){return this.dispatchEvent({type:"disconnected",data:e}),this._targetRay!==null&&(this._targetRay.visible=!1),this._grip!==null&&(this._grip.visible=!1),this._hand!==null&&(this._hand.visible=!1),this}update(e,t,n){let i=null,r=null,o=null;const a=this._targetRay,l=this._grip,c=this._hand;if(e&&t.session.visibilityState!=="visible-blurred"){if(c&&e.hand){o=!0;for(const x of e.hand.values()){const p=t.getJointPose(x,n),m=this._getHandJoint(c,x);p!==null&&(m.matrix.fromArray(p.transform.matrix),m.matrix.decompose(m.position,m.rotation,m.scale),m.matrixWorldNeedsUpdate=!0,m.jointRadius=p.radius),m.visible=p!==null}const h=c.joints["index-finger-tip"],u=c.joints["thumb-tip"],d=h.position.distanceTo(u.position),f=.02,g=.005;c.inputState.pinching&&d>f+g?(c.inputState.pinching=!1,this.dispatchEvent({type:"pinchend",handedness:e.handedness,target:this})):!c.inputState.pinching&&d<=f-g&&(c.inputState.pinching=!0,this.dispatchEvent({type:"pinchstart",handedness:e.handedness,target:this}))}else l!==null&&e.gripSpace&&(r=t.getPose(e.gripSpace,n),r!==null&&(l.matrix.fromArray(r.transform.matrix),l.matrix.decompose(l.position,l.rotation,l.scale),l.matrixWorldNeedsUpdate=!0,r.linearVelocity?(l.hasLinearVelocity=!0,l.linearVelocity.copy(r.linearVelocity)):l.hasLinearVelocity=!1,r.angularVelocity?(l.hasAngularVelocity=!0,l.angularVelocity.copy(r.angularVelocity)):l.hasAngularVelocity=!1));a!==null&&(i=t.getPose(e.targetRaySpace,n),i===null&&r!==null&&(i=r),i!==null&&(a.matrix.fromArray(i.transform.matrix),a.matrix.decompose(a.position,a.rotation,a.scale),a.matrixWorldNeedsUpdate=!0,i.linearVelocity?(a.hasLinearVelocity=!0,a.linearVelocity.copy(i.linearVelocity)):a.hasLinearVelocity=!1,i.angularVelocity?(a.hasAngularVelocity=!0,a.angularVelocity.copy(i.angularVelocity)):a.hasAngularVelocity=!1,this.dispatchEvent(Rg)))}return a!==null&&(a.visible=i!==null),l!==null&&(l.visible=r!==null),c!==null&&(c.visible=o!==null),this}_getHandJoint(e,t){if(e.joints[t.jointName]===void 0){const n=new qe;n.matrixAutoUpdate=!1,n.visible=!1,e.joints[t.jointName]=n,e.add(n)}return e.joints[t.jointName]}}const Dg=`
void main() {

	gl_Position = vec4( position, 1.0 );

}`,Ig=`
uniform sampler2DArray depthColor;
uniform float depthWidth;
uniform float depthHeight;

void main() {

	vec2 coord = vec2( gl_FragCoord.x / depthWidth, gl_FragCoord.y / depthHeight );

	if ( coord.x >= 1.0 ) {

		gl_FragDepth = texture( depthColor, vec3( coord.x - 1.0, coord.y, 1 ) ).r;

	} else {

		gl_FragDepth = texture( depthColor, vec3( coord.x, coord.y, 0 ) ).r;

	}

}`;class Lg{constructor(){this.texture=null,this.mesh=null,this.depthNear=0,this.depthFar=0}init(e,t,n){if(this.texture===null){const i=new It,r=e.properties.get(i);r.__webglTexture=t.texture,(t.depthNear!=n.depthNear||t.depthFar!=n.depthFar)&&(this.depthNear=t.depthNear,this.depthFar=t.depthFar),this.texture=i}}getMesh(e){if(this.texture!==null&&this.mesh===null){const t=e.cameras[0].viewport,n=new gt({vertexShader:Dg,fragmentShader:Ig,uniforms:{depthColor:{value:this.texture},depthWidth:{value:t.z},depthHeight:{value:t.w}}});this.mesh=new ve(new Gt(20,20),n)}return this.mesh}reset(){this.texture=null,this.mesh=null}getDepthTexture(){return this.texture}}class Ng extends _i{constructor(e,t){super();const n=this;let i=null,r=1,o=null,a="local-floor",l=1,c=null,h=null,u=null,d=null,f=null,g=null;const x=new Lg,p=t.getContextAttributes();let m=null,_=null;const v=[],M=[],S=new Q;let E=null;const C=new Jt;C.layers.enable(1),C.viewport=new ot;const z=new Jt;z.layers.enable(2),z.viewport=new ot;const T=[C,z],y=new Pg;y.layers.enable(1),y.layers.enable(2);let b=null,D=null;this.cameraAutoUpdate=!0,this.enabled=!1,this.isPresenting=!1,this.getController=function(W){let $=v[W];return $===void 0&&($=new Lo,v[W]=$),$.getTargetRaySpace()},this.getControllerGrip=function(W){let $=v[W];return $===void 0&&($=new Lo,v[W]=$),$.getGripSpace()},this.getHand=function(W){let $=v[W];return $===void 0&&($=new Lo,v[W]=$),$.getHandSpace()};function L(W){const $=M.indexOf(W.inputSource);if($===-1)return;const le=v[$];le!==void 0&&(le.update(W.inputSource,W.frame,c||o),le.dispatchEvent({type:W.type,data:W.inputSource}))}function N(){i.removeEventListener("select",L),i.removeEventListener("selectstart",L),i.removeEventListener("selectend",L),i.removeEventListener("squeeze",L),i.removeEventListener("squeezestart",L),i.removeEventListener("squeezeend",L),i.removeEventListener("end",N),i.removeEventListener("inputsourceschange",B);for(let W=0;W<v.length;W++){const $=M[W];$!==null&&(M[W]=null,v[W].disconnect($))}b=null,D=null,x.reset(),e.setRenderTarget(m),f=null,d=null,u=null,i=null,_=null,Z.stop(),n.isPresenting=!1,e.setPixelRatio(E),e.setSize(S.width,S.height,!1),n.dispatchEvent({type:"sessionend"})}this.setFramebufferScaleFactor=function(W){r=W,n.isPresenting===!0&&console.warn("THREE.WebXRManager: Cannot change framebuffer scale while presenting.")},this.setReferenceSpaceType=function(W){a=W,n.isPresenting===!0&&console.warn("THREE.WebXRManager: Cannot change reference space type while presenting.")},this.getReferenceSpace=function(){return c||o},this.setReferenceSpace=function(W){c=W},this.getBaseLayer=function(){return d!==null?d:f},this.getBinding=function(){return u},this.getFrame=function(){return g},this.getSession=function(){return i},this.setSession=async function(W){if(i=W,i!==null){if(m=e.getRenderTarget(),i.addEventListener("select",L),i.addEventListener("selectstart",L),i.addEventListener("selectend",L),i.addEventListener("squeeze",L),i.addEventListener("squeezestart",L),i.addEventListener("squeezeend",L),i.addEventListener("end",N),i.addEventListener("inputsourceschange",B),p.xrCompatible!==!0&&await t.makeXRCompatible(),E=e.getPixelRatio(),e.getSize(S),i.renderState.layers===void 0){const $={antialias:p.antialias,alpha:!0,depth:p.depth,stencil:p.stencil,framebufferScaleFactor:r};f=new XRWebGLLayer(i,t,$),i.updateRenderState({baseLayer:f}),e.setPixelRatio(1),e.setSize(f.framebufferWidth,f.framebufferHeight,!1),_=new un(f.framebufferWidth,f.framebufferHeight,{format:sn,type:Vn,colorSpace:e.outputColorSpace,stencilBuffer:p.stencil})}else{let $=null,le=null,he=null;p.depth&&(he=p.stencil?t.DEPTH24_STENCIL8:t.DEPTH_COMPONENT24,$=p.stencil?ts:ji,le=p.stencil?es:gi);const Ce={colorFormat:t.RGBA8,depthFormat:he,scaleFactor:r};u=new XRWebGLBinding(i,t),d=u.createProjectionLayer(Ce),i.updateRenderState({layers:[d]}),e.setPixelRatio(1),e.setSize(d.textureWidth,d.textureHeight,!1),_=new un(d.textureWidth,d.textureHeight,{format:sn,type:Vn,depthTexture:new zh(d.textureWidth,d.textureHeight,le,void 0,void 0,void 0,void 0,void 0,void 0,$),stencilBuffer:p.stencil,colorSpace:e.outputColorSpace,samples:p.antialias?4:0,resolveDepthBuffer:d.ignoreDepthValues===!1})}_.isXRRenderTarget=!0,this.setFoveation(l),c=null,o=await i.requestReferenceSpace(a),Z.setContext(i),Z.start(),n.isPresenting=!0,n.dispatchEvent({type:"sessionstart"})}},this.getEnvironmentBlendMode=function(){if(i!==null)return i.environmentBlendMode},this.getDepthTexture=function(){return x.getDepthTexture()};function B(W){for(let $=0;$<W.removed.length;$++){const le=W.removed[$],he=M.indexOf(le);he>=0&&(M[he]=null,v[he].disconnect(le))}for(let $=0;$<W.added.length;$++){const le=W.added[$];let he=M.indexOf(le);if(he===-1){for(let Oe=0;Oe<v.length;Oe++)if(Oe>=M.length){M.push(le),he=Oe;break}else if(M[Oe]===null){M[Oe]=le,he=Oe;break}if(he===-1)break}const Ce=v[he];Ce&&Ce.connect(le)}}const k=new w,q=new w;function U(W,$,le){k.setFromMatrixPosition($.matrixWorld),q.setFromMatrixPosition(le.matrixWorld);const he=k.distanceTo(q),Ce=$.projectionMatrix.elements,Oe=le.projectionMatrix.elements,Ie=Ce[14]/(Ce[10]-1),ze=Ce[14]/(Ce[10]+1),te=(Ce[9]+1)/Ce[5],I=(Ce[9]-1)/Ce[5],ce=(Ce[8]-1)/Ce[0],ae=(Oe[8]+1)/Oe[0],se=Ie*ce,de=Ie*ae,xe=he/(-ce+ae),pe=xe*-ce;if($.matrixWorld.decompose(W.position,W.quaternion,W.scale),W.translateX(pe),W.translateZ(xe),W.matrixWorld.compose(W.position,W.quaternion,W.scale),W.matrixWorldInverse.copy(W.matrixWorld).invert(),Ce[10]===-1)W.projectionMatrix.copy($.projectionMatrix),W.projectionMatrixInverse.copy($.projectionMatrixInverse);else{const F=Ie+xe,A=ze+xe,j=se-pe,ne=de+(he-pe),re=te*ze/A*F,ie=I*ze/A*F;W.projectionMatrix.makePerspective(j,ne,re,ie,F,A),W.projectionMatrixInverse.copy(W.projectionMatrix).invert()}}function V(W,$){$===null?W.matrixWorld.copy(W.matrix):W.matrixWorld.multiplyMatrices($.matrixWorld,W.matrix),W.matrixWorldInverse.copy(W.matrixWorld).invert()}this.updateCamera=function(W){if(i===null)return;let $=W.near,le=W.far;x.texture!==null&&(x.depthNear>0&&($=x.depthNear),x.depthFar>0&&(le=x.depthFar)),y.near=z.near=C.near=$,y.far=z.far=C.far=le,(b!==y.near||D!==y.far)&&(i.updateRenderState({depthNear:y.near,depthFar:y.far}),b=y.near,D=y.far);const he=W.parent,Ce=y.cameras;V(y,he);for(let Oe=0;Oe<Ce.length;Oe++)V(Ce[Oe],he);Ce.length===2?U(y,C,z):y.projectionMatrix.copy(C.projectionMatrix),P(W,y,he)};function P(W,$,le){le===null?W.matrix.copy($.matrixWorld):(W.matrix.copy(le.matrixWorld),W.matrix.invert(),W.matrix.multiply($.matrixWorld)),W.matrix.decompose(W.position,W.quaternion,W.scale),W.updateMatrixWorld(!0),W.projectionMatrix.copy($.projectionMatrix),W.projectionMatrixInverse.copy($.projectionMatrixInverse),W.isPerspectiveCamera&&(W.fov=ns*2*Math.atan(1/W.projectionMatrix.elements[5]),W.zoom=1)}this.getCamera=function(){return y},this.getFoveation=function(){if(!(d===null&&f===null))return l},this.setFoveation=function(W){l=W,d!==null&&(d.fixedFoveation=W),f!==null&&f.fixedFoveation!==void 0&&(f.fixedFoveation=W)},this.hasDepthSensing=function(){return x.texture!==null},this.getDepthSensingMesh=function(){return x.getMesh(y)};let O=null;function H(W,$){if(h=$.getViewerPose(c||o),g=$,h!==null){const le=h.views;f!==null&&(e.setRenderTargetFramebuffer(_,f.framebuffer),e.setRenderTarget(_));let he=!1;le.length!==y.cameras.length&&(y.cameras.length=0,he=!0);for(let Oe=0;Oe<le.length;Oe++){const Ie=le[Oe];let ze=null;if(f!==null)ze=f.getViewport(Ie);else{const I=u.getViewSubImage(d,Ie);ze=I.viewport,Oe===0&&(e.setRenderTargetTextures(_,I.colorTexture,d.ignoreDepthValues?void 0:I.depthStencilTexture),e.setRenderTarget(_))}let te=T[Oe];te===void 0&&(te=new Jt,te.layers.enable(Oe),te.viewport=new ot,T[Oe]=te),te.matrix.fromArray(Ie.transform.matrix),te.matrix.decompose(te.position,te.quaternion,te.scale),te.projectionMatrix.fromArray(Ie.projectionMatrix),te.projectionMatrixInverse.copy(te.projectionMatrix).invert(),te.viewport.set(ze.x,ze.y,ze.width,ze.height),Oe===0&&(y.matrix.copy(te.matrix),y.matrix.decompose(y.position,y.quaternion,y.scale)),he===!0&&y.cameras.push(te)}const Ce=i.enabledFeatures;if(Ce&&Ce.includes("depth-sensing")){const Oe=u.getDepthInformation(le[0]);Oe&&Oe.isValid&&Oe.texture&&x.init(e,Oe,i.renderState)}}for(let le=0;le<v.length;le++){const he=M[le],Ce=v[le];he!==null&&Ce!==void 0&&Ce.update(he,$,c||o)}O&&O(W,$),$.detectedPlanes&&n.dispatchEvent({type:"planesdetected",data:$}),g=null}const Z=new Fh;Z.setAnimationLoop(H),this.setAnimationLoop=function(W){O=W},this.dispose=function(){}}}const ci=new Yt,Ug=new Fe;function Og(s,e){function t(p,m){p.matrixAutoUpdate===!0&&p.updateMatrix(),m.value.copy(p.matrix)}function n(p,m){m.color.getRGB(p.fogColor.value,Nh(s)),m.isFog?(p.fogNear.value=m.near,p.fogFar.value=m.far):m.isFogExp2&&(p.fogDensity.value=m.density)}function i(p,m,_,v,M){m.isMeshBasicMaterial||m.isMeshLambertMaterial?r(p,m):m.isMeshToonMaterial?(r(p,m),u(p,m)):m.isMeshPhongMaterial?(r(p,m),h(p,m)):m.isMeshStandardMaterial?(r(p,m),d(p,m),m.isMeshPhysicalMaterial&&f(p,m,M)):m.isMeshMatcapMaterial?(r(p,m),g(p,m)):m.isMeshDepthMaterial?r(p,m):m.isMeshDistanceMaterial?(r(p,m),x(p,m)):m.isMeshNormalMaterial?r(p,m):m.isLineBasicMaterial?(o(p,m),m.isLineDashedMaterial&&a(p,m)):m.isPointsMaterial?l(p,m,_,v):m.isSpriteMaterial?c(p,m):m.isShadowMaterial?(p.color.value.copy(m.color),p.opacity.value=m.opacity):m.isShaderMaterial&&(m.uniformsNeedUpdate=!1)}function r(p,m){p.opacity.value=m.opacity,m.color&&p.diffuse.value.copy(m.color),m.emissive&&p.emissive.value.copy(m.emissive).multiplyScalar(m.emissiveIntensity),m.map&&(p.map.value=m.map,t(m.map,p.mapTransform)),m.alphaMap&&(p.alphaMap.value=m.alphaMap,t(m.alphaMap,p.alphaMapTransform)),m.bumpMap&&(p.bumpMap.value=m.bumpMap,t(m.bumpMap,p.bumpMapTransform),p.bumpScale.value=m.bumpScale,m.side===Ht&&(p.bumpScale.value*=-1)),m.normalMap&&(p.normalMap.value=m.normalMap,t(m.normalMap,p.normalMapTransform),p.normalScale.value.copy(m.normalScale),m.side===Ht&&p.normalScale.value.negate()),m.displacementMap&&(p.displacementMap.value=m.displacementMap,t(m.displacementMap,p.displacementMapTransform),p.displacementScale.value=m.displacementScale,p.displacementBias.value=m.displacementBias),m.emissiveMap&&(p.emissiveMap.value=m.emissiveMap,t(m.emissiveMap,p.emissiveMapTransform)),m.specularMap&&(p.specularMap.value=m.specularMap,t(m.specularMap,p.specularMapTransform)),m.alphaTest>0&&(p.alphaTest.value=m.alphaTest);const _=e.get(m),v=_.envMap,M=_.envMapRotation;v&&(p.envMap.value=v,ci.copy(M),ci.x*=-1,ci.y*=-1,ci.z*=-1,v.isCubeTexture&&v.isRenderTargetTexture===!1&&(ci.y*=-1,ci.z*=-1),p.envMapRotation.value.setFromMatrix4(Ug.makeRotationFromEuler(ci)),p.flipEnvMap.value=v.isCubeTexture&&v.isRenderTargetTexture===!1?-1:1,p.reflectivity.value=m.reflectivity,p.ior.value=m.ior,p.refractionRatio.value=m.refractionRatio),m.lightMap&&(p.lightMap.value=m.lightMap,p.lightMapIntensity.value=m.lightMapIntensity,t(m.lightMap,p.lightMapTransform)),m.aoMap&&(p.aoMap.value=m.aoMap,p.aoMapIntensity.value=m.aoMapIntensity,t(m.aoMap,p.aoMapTransform))}function o(p,m){p.diffuse.value.copy(m.color),p.opacity.value=m.opacity,m.map&&(p.map.value=m.map,t(m.map,p.mapTransform))}function a(p,m){p.dashSize.value=m.dashSize,p.totalSize.value=m.dashSize+m.gapSize,p.scale.value=m.scale}function l(p,m,_,v){p.diffuse.value.copy(m.color),p.opacity.value=m.opacity,p.size.value=m.size*_,p.scale.value=v*.5,m.map&&(p.map.value=m.map,t(m.map,p.uvTransform)),m.alphaMap&&(p.alphaMap.value=m.alphaMap,t(m.alphaMap,p.alphaMapTransform)),m.alphaTest>0&&(p.alphaTest.value=m.alphaTest)}function c(p,m){p.diffuse.value.copy(m.color),p.opacity.value=m.opacity,p.rotation.value=m.rotation,m.map&&(p.map.value=m.map,t(m.map,p.mapTransform)),m.alphaMap&&(p.alphaMap.value=m.alphaMap,t(m.alphaMap,p.alphaMapTransform)),m.alphaTest>0&&(p.alphaTest.value=m.alphaTest)}function h(p,m){p.specular.value.copy(m.specular),p.shininess.value=Math.max(m.shininess,1e-4)}function u(p,m){m.gradientMap&&(p.gradientMap.value=m.gradientMap)}function d(p,m){p.metalness.value=m.metalness,m.metalnessMap&&(p.metalnessMap.value=m.metalnessMap,t(m.metalnessMap,p.metalnessMapTransform)),p.roughness.value=m.roughness,m.roughnessMap&&(p.roughnessMap.value=m.roughnessMap,t(m.roughnessMap,p.roughnessMapTransform)),m.envMap&&(p.envMapIntensity.value=m.envMapIntensity)}function f(p,m,_){p.ior.value=m.ior,m.sheen>0&&(p.sheenColor.value.copy(m.sheenColor).multiplyScalar(m.sheen),p.sheenRoughness.value=m.sheenRoughness,m.sheenColorMap&&(p.sheenColorMap.value=m.sheenColorMap,t(m.sheenColorMap,p.sheenColorMapTransform)),m.sheenRoughnessMap&&(p.sheenRoughnessMap.value=m.sheenRoughnessMap,t(m.sheenRoughnessMap,p.sheenRoughnessMapTransform))),m.clearcoat>0&&(p.clearcoat.value=m.clearcoat,p.clearcoatRoughness.value=m.clearcoatRoughness,m.clearcoatMap&&(p.clearcoatMap.value=m.clearcoatMap,t(m.clearcoatMap,p.clearcoatMapTransform)),m.clearcoatRoughnessMap&&(p.clearcoatRoughnessMap.value=m.clearcoatRoughnessMap,t(m.clearcoatRoughnessMap,p.clearcoatRoughnessMapTransform)),m.clearcoatNormalMap&&(p.clearcoatNormalMap.value=m.clearcoatNormalMap,t(m.clearcoatNormalMap,p.clearcoatNormalMapTransform),p.clearcoatNormalScale.value.copy(m.clearcoatNormalScale),m.side===Ht&&p.clearcoatNormalScale.value.negate())),m.dispersion>0&&(p.dispersion.value=m.dispersion),m.iridescence>0&&(p.iridescence.value=m.iridescence,p.iridescenceIOR.value=m.iridescenceIOR,p.iridescenceThicknessMinimum.value=m.iridescenceThicknessRange[0],p.iridescenceThicknessMaximum.value=m.iridescenceThicknessRange[1],m.iridescenceMap&&(p.iridescenceMap.value=m.iridescenceMap,t(m.iridescenceMap,p.iridescenceMapTransform)),m.iridescenceThicknessMap&&(p.iridescenceThicknessMap.value=m.iridescenceThicknessMap,t(m.iridescenceThicknessMap,p.iridescenceThicknessMapTransform))),m.transmission>0&&(p.transmission.value=m.transmission,p.transmissionSamplerMap.value=_.texture,p.transmissionSamplerSize.value.set(_.width,_.height),m.transmissionMap&&(p.transmissionMap.value=m.transmissionMap,t(m.transmissionMap,p.transmissionMapTransform)),p.thickness.value=m.thickness,m.thicknessMap&&(p.thicknessMap.value=m.thicknessMap,t(m.thicknessMap,p.thicknessMapTransform)),p.attenuationDistance.value=m.attenuationDistance,p.attenuationColor.value.copy(m.attenuationColor)),m.anisotropy>0&&(p.anisotropyVector.value.set(m.anisotropy*Math.cos(m.anisotropyRotation),m.anisotropy*Math.sin(m.anisotropyRotation)),m.anisotropyMap&&(p.anisotropyMap.value=m.anisotropyMap,t(m.anisotropyMap,p.anisotropyMapTransform))),p.specularIntensity.value=m.specularIntensity,p.specularColor.value.copy(m.specularColor),m.specularColorMap&&(p.specularColorMap.value=m.specularColorMap,t(m.specularColorMap,p.specularColorMapTransform)),m.specularIntensityMap&&(p.specularIntensityMap.value=m.specularIntensityMap,t(m.specularIntensityMap,p.specularIntensityMapTransform))}function g(p,m){m.matcap&&(p.matcap.value=m.matcap)}function x(p,m){const _=e.get(m).light;p.referencePosition.value.setFromMatrixPosition(_.matrixWorld),p.nearDistance.value=_.shadow.camera.near,p.farDistance.value=_.shadow.camera.far}return{refreshFogUniforms:n,refreshMaterialUniforms:i}}function Fg(s,e,t,n){let i={},r={},o=[];const a=s.getParameter(s.MAX_UNIFORM_BUFFER_BINDINGS);function l(_,v){const M=v.program;n.uniformBlockBinding(_,M)}function c(_,v){let M=i[_.id];M===void 0&&(g(_),M=h(_),i[_.id]=M,_.addEventListener("dispose",p));const S=v.program;n.updateUBOMapping(_,S);const E=e.render.frame;r[_.id]!==E&&(d(_),r[_.id]=E)}function h(_){const v=u();_.__bindingPointIndex=v;const M=s.createBuffer(),S=_.__size,E=_.usage;return s.bindBuffer(s.UNIFORM_BUFFER,M),s.bufferData(s.UNIFORM_BUFFER,S,E),s.bindBuffer(s.UNIFORM_BUFFER,null),s.bindBufferBase(s.UNIFORM_BUFFER,v,M),M}function u(){for(let _=0;_<a;_++)if(o.indexOf(_)===-1)return o.push(_),_;return console.error("THREE.WebGLRenderer: Maximum number of simultaneously usable uniforms groups reached."),0}function d(_){const v=i[_.id],M=_.uniforms,S=_.__cache;s.bindBuffer(s.UNIFORM_BUFFER,v);for(let E=0,C=M.length;E<C;E++){const z=Array.isArray(M[E])?M[E]:[M[E]];for(let T=0,y=z.length;T<y;T++){const b=z[T];if(f(b,E,T,S)===!0){const D=b.__offset,L=Array.isArray(b.value)?b.value:[b.value];let N=0;for(let B=0;B<L.length;B++){const k=L[B],q=x(k);typeof k=="number"||typeof k=="boolean"?(b.__data[0]=k,s.bufferSubData(s.UNIFORM_BUFFER,D+N,b.__data)):k.isMatrix3?(b.__data[0]=k.elements[0],b.__data[1]=k.elements[1],b.__data[2]=k.elements[2],b.__data[3]=0,b.__data[4]=k.elements[3],b.__data[5]=k.elements[4],b.__data[6]=k.elements[5],b.__data[7]=0,b.__data[8]=k.elements[6],b.__data[9]=k.elements[7],b.__data[10]=k.elements[8],b.__data[11]=0):(k.toArray(b.__data,N),N+=q.storage/Float32Array.BYTES_PER_ELEMENT)}s.bufferSubData(s.UNIFORM_BUFFER,D,b.__data)}}}s.bindBuffer(s.UNIFORM_BUFFER,null)}function f(_,v,M,S){const E=_.value,C=v+"_"+M;if(S[C]===void 0)return typeof E=="number"||typeof E=="boolean"?S[C]=E:S[C]=E.clone(),!0;{const z=S[C];if(typeof E=="number"||typeof E=="boolean"){if(z!==E)return S[C]=E,!0}else if(z.equals(E)===!1)return z.copy(E),!0}return!1}function g(_){const v=_.uniforms;let M=0;const S=16;for(let C=0,z=v.length;C<z;C++){const T=Array.isArray(v[C])?v[C]:[v[C]];for(let y=0,b=T.length;y<b;y++){const D=T[y],L=Array.isArray(D.value)?D.value:[D.value];for(let N=0,B=L.length;N<B;N++){const k=L[N],q=x(k),U=M%S,V=U%q.boundary,P=U+V;M+=V,P!==0&&S-P<q.storage&&(M+=S-P),D.__data=new Float32Array(q.storage/Float32Array.BYTES_PER_ELEMENT),D.__offset=M,M+=q.storage}}}const E=M%S;return E>0&&(M+=S-E),_.__size=M,_.__cache={},this}function x(_){const v={boundary:0,storage:0};return typeof _=="number"||typeof _=="boolean"?(v.boundary=4,v.storage=4):_.isVector2?(v.boundary=8,v.storage=8):_.isVector3||_.isColor?(v.boundary=16,v.storage=12):_.isVector4?(v.boundary=16,v.storage=16):_.isMatrix3?(v.boundary=48,v.storage=48):_.isMatrix4?(v.boundary=64,v.storage=64):_.isTexture?console.warn("THREE.WebGLRenderer: Texture samplers can not be part of an uniforms group."):console.warn("THREE.WebGLRenderer: Unsupported uniform value type.",_),v}function p(_){const v=_.target;v.removeEventListener("dispose",p);const M=o.indexOf(v.__bindingPointIndex);o.splice(M,1),s.deleteBuffer(i[v.id]),delete i[v.id],delete r[v.id]}function m(){for(const _ in i)s.deleteBuffer(i[_]);o=[],i={},r={}}return{bind:l,update:c,dispose:m}}class zg{constructor(e={}){const{canvas:t=bd(),context:n=null,depth:i=!0,stencil:r=!1,alpha:o=!1,antialias:a=!1,premultipliedAlpha:l=!0,preserveDrawingBuffer:c=!1,powerPreference:h="default",failIfMajorPerformanceCaveat:u=!1}=e;this.isWebGLRenderer=!0;let d;if(n!==null){if(typeof WebGLRenderingContext<"u"&&n instanceof WebGLRenderingContext)throw new Error("THREE.WebGLRenderer: WebGL 1 is not supported since r163.");d=n.getContextAttributes().alpha}else d=o;const f=new Uint32Array(4),g=new Int32Array(4);let x=null,p=null;const m=[],_=[];this.domElement=t,this.debug={checkShaderErrors:!0,onShaderError:null},this.autoClear=!0,this.autoClearColor=!0,this.autoClearDepth=!0,this.autoClearStencil=!0,this.sortObjects=!0,this.clippingPlanes=[],this.localClippingEnabled=!1,this._outputColorSpace=Ft,this.toneMapping=ei,this.toneMappingExposure=1;const v=this;let M=!1,S=0,E=0,C=null,z=-1,T=null;const y=new ot,b=new ot;let D=null;const L=new Ne(0);let N=0,B=t.width,k=t.height,q=1,U=null,V=null;const P=new ot(0,0,B,k),O=new ot(0,0,B,k);let H=!1;const Z=new el;let W=!1,$=!1;const le=new Fe,he=new Fe,Ce=new w,Oe=new ot,Ie={background:null,fog:null,environment:null,overrideMaterial:null,isScene:!0};let ze=!1;function te(){return C===null?q:1}let I=n;function ce(R,X){return t.getContext(R,X)}try{const R={alpha:!0,depth:i,stencil:r,antialias:a,premultipliedAlpha:l,preserveDrawingBuffer:c,powerPreference:h,failIfMajorPerformanceCaveat:u};if("setAttribute"in t&&t.setAttribute("data-engine",`three.js r${Ga}`),t.addEventListener("webglcontextlost",oe,!1),t.addEventListener("webglcontextrestored",_e,!1),t.addEventListener("webglcontextcreationerror",be,!1),I===null){const X="webgl2";if(I=ce(X,R),I===null)throw ce(X)?new Error("Error creating WebGL context with your selected attributes."):new Error("Error creating WebGL context.")}}catch(R){throw console.error("THREE.WebGLRenderer: "+R.message),R}let ae,se,de,xe,pe,F,A,j,ne,re,ie,Pe,me,we,Ze,ue,Se,Ve,He,Te,Je,We,ht,G;function Me(){ae=new Gp(I),ae.init(),We=new Cg(I,ae),se=new Fp(I,ae,e,We),de=new Tg(I),se.reverseDepthBuffer&&de.buffers.depth.setReversed(!0),xe=new Yp(I),pe=new hg,F=new Ag(I,ae,de,pe,se,We,xe),A=new kp(v),j=new Hp(v),ne=new $d(I),ht=new Up(I,ne),re=new Wp(I,ne,xe,ht),ie=new jp(I,re,ne,xe),He=new qp(I,se,F),ue=new zp(pe),Pe=new cg(v,A,j,ae,se,ht,ue),me=new Og(v,pe),we=new dg,Ze=new xg(ae),Ve=new Np(v,A,j,de,ie,d,l),Se=new wg(v,ie,se),G=new Fg(I,xe,se,de),Te=new Op(I,ae,xe),Je=new Xp(I,ae,xe),xe.programs=Pe.programs,v.capabilities=se,v.extensions=ae,v.properties=pe,v.renderLists=we,v.shadowMap=Se,v.state=de,v.info=xe}Me();const ee=new Ng(v,I);this.xr=ee,this.getContext=function(){return I},this.getContextAttributes=function(){return I.getContextAttributes()},this.forceContextLoss=function(){const R=ae.get("WEBGL_lose_context");R&&R.loseContext()},this.forceContextRestore=function(){const R=ae.get("WEBGL_lose_context");R&&R.restoreContext()},this.getPixelRatio=function(){return q},this.setPixelRatio=function(R){R!==void 0&&(q=R,this.setSize(B,k,!1))},this.getSize=function(R){return R.set(B,k)},this.setSize=function(R,X,K=!0){if(ee.isPresenting){console.warn("THREE.WebGLRenderer: Can't change size while VR device is presenting.");return}B=R,k=X,t.width=Math.floor(R*q),t.height=Math.floor(X*q),K===!0&&(t.style.width=R+"px",t.style.height=X+"px"),this.setViewport(0,0,R,X)},this.getDrawingBufferSize=function(R){return R.set(B*q,k*q).floor()},this.setDrawingBufferSize=function(R,X,K){B=R,k=X,q=K,t.width=Math.floor(R*K),t.height=Math.floor(X*K),this.setViewport(0,0,R,X)},this.getCurrentViewport=function(R){return R.copy(y)},this.getViewport=function(R){return R.copy(P)},this.setViewport=function(R,X,K,J){R.isVector4?P.set(R.x,R.y,R.z,R.w):P.set(R,X,K,J),de.viewport(y.copy(P).multiplyScalar(q).round())},this.getScissor=function(R){return R.copy(O)},this.setScissor=function(R,X,K,J){R.isVector4?O.set(R.x,R.y,R.z,R.w):O.set(R,X,K,J),de.scissor(b.copy(O).multiplyScalar(q).round())},this.getScissorTest=function(){return H},this.setScissorTest=function(R){de.setScissorTest(H=R)},this.setOpaqueSort=function(R){U=R},this.setTransparentSort=function(R){V=R},this.getClearColor=function(R){return R.copy(Ve.getClearColor())},this.setClearColor=function(){Ve.setClearColor.apply(Ve,arguments)},this.getClearAlpha=function(){return Ve.getClearAlpha()},this.setClearAlpha=function(){Ve.setClearAlpha.apply(Ve,arguments)},this.clear=function(R=!0,X=!0,K=!0){let J=0;if(R){let Y=!1;if(C!==null){const fe=C.texture.format;Y=fe===Za||fe===Ka||fe===ja}if(Y){const fe=C.texture.type,ye=fe===Vn||fe===gi||fe===Ds||fe===es||fe===Xa||fe===Ya,Ee=Ve.getClearColor(),Re=Ve.getClearAlpha(),ke=Ee.r,Be=Ee.g,Le=Ee.b;ye?(f[0]=ke,f[1]=Be,f[2]=Le,f[3]=Re,I.clearBufferuiv(I.COLOR,0,f)):(g[0]=ke,g[1]=Be,g[2]=Le,g[3]=Re,I.clearBufferiv(I.COLOR,0,g))}else J|=I.COLOR_BUFFER_BIT}X&&(J|=I.DEPTH_BUFFER_BIT,I.clearDepth(this.capabilities.reverseDepthBuffer?0:1)),K&&(J|=I.STENCIL_BUFFER_BIT,this.state.buffers.stencil.setMask(4294967295)),I.clear(J)},this.clearColor=function(){this.clear(!0,!1,!1)},this.clearDepth=function(){this.clear(!1,!0,!1)},this.clearStencil=function(){this.clear(!1,!1,!0)},this.dispose=function(){t.removeEventListener("webglcontextlost",oe,!1),t.removeEventListener("webglcontextrestored",_e,!1),t.removeEventListener("webglcontextcreationerror",be,!1),we.dispose(),Ze.dispose(),pe.dispose(),A.dispose(),j.dispose(),ie.dispose(),ht.dispose(),G.dispose(),Pe.dispose(),ee.dispose(),ee.removeEventListener("sessionstart",gl),ee.removeEventListener("sessionend",vl),ii.stop()};function oe(R){R.preventDefault(),console.log("THREE.WebGLRenderer: Context Lost."),M=!0}function _e(){console.log("THREE.WebGLRenderer: Context Restored."),M=!1;const R=xe.autoReset,X=Se.enabled,K=Se.autoUpdate,J=Se.needsUpdate,Y=Se.type;Me(),xe.autoReset=R,Se.enabled=X,Se.autoUpdate=K,Se.needsUpdate=J,Se.type=Y}function be(R){console.error("THREE.WebGLRenderer: A WebGL context could not be created. Reason: ",R.statusMessage)}function Qe(R){const X=R.target;X.removeEventListener("dispose",Qe),Et(X)}function Et(R){jt(R),pe.remove(R)}function jt(R){const X=pe.get(R).programs;X!==void 0&&(X.forEach(function(K){Pe.releaseProgram(K)}),R.isShaderMaterial&&Pe.releaseShaderCache(R))}this.renderBufferDirect=function(R,X,K,J,Y,fe){X===null&&(X=Ie);const ye=Y.isMesh&&Y.matrixWorld.determinant()<0,Ee=fu(R,X,K,J,Y);de.setMaterial(J,ye);let Re=K.index,ke=1;if(J.wireframe===!0){if(Re=re.getWireframeAttribute(K),Re===void 0)return;ke=2}const Be=K.drawRange,Le=K.attributes.position;let rt=Be.start*ke,pt=(Be.start+Be.count)*ke;fe!==null&&(rt=Math.max(rt,fe.start*ke),pt=Math.min(pt,(fe.start+fe.count)*ke)),Re!==null?(rt=Math.max(rt,0),pt=Math.min(pt,Re.count)):Le!=null&&(rt=Math.max(rt,0),pt=Math.min(pt,Le.count));const bt=pt-rt;if(bt<0||bt===1/0)return;ht.setup(Y,J,Ee,K,Re);let Qt,it=Te;if(Re!==null&&(Qt=ne.get(Re),it=Je,it.setIndex(Qt)),Y.isMesh)J.wireframe===!0?(de.setLineWidth(J.wireframeLinewidth*te()),it.setMode(I.LINES)):it.setMode(I.TRIANGLES);else if(Y.isLine){let Ue=J.linewidth;Ue===void 0&&(Ue=1),de.setLineWidth(Ue*te()),Y.isLineSegments?it.setMode(I.LINES):Y.isLineLoop?it.setMode(I.LINE_LOOP):it.setMode(I.LINE_STRIP)}else Y.isPoints?it.setMode(I.POINTS):Y.isSprite&&it.setMode(I.TRIANGLES);if(Y.isBatchedMesh)if(Y._multiDrawInstances!==null)it.renderMultiDrawInstances(Y._multiDrawStarts,Y._multiDrawCounts,Y._multiDrawCount,Y._multiDrawInstances);else if(ae.get("WEBGL_multi_draw"))it.renderMultiDraw(Y._multiDrawStarts,Y._multiDrawCounts,Y._multiDrawCount);else{const Ue=Y._multiDrawStarts,zt=Y._multiDrawCounts,st=Y._multiDrawCount,dn=Re?ne.get(Re).bytesPerElement:1,Ti=pe.get(J).currentProgram.getUniforms();for(let en=0;en<st;en++)Ti.setValue(I,"_gl_DrawID",en),it.render(Ue[en]/dn,zt[en])}else if(Y.isInstancedMesh)it.renderInstances(rt,bt,Y.count);else if(K.isInstancedBufferGeometry){const Ue=K._maxInstanceCount!==void 0?K._maxInstanceCount:1/0,zt=Math.min(K.instanceCount,Ue);it.renderInstances(rt,bt,zt)}else it.render(rt,bt)};function tt(R,X,K){R.transparent===!0&&R.side===Dt&&R.forceSinglePass===!1?(R.side=Ht,R.needsUpdate=!0,Bs(R,X,K),R.side=wn,R.needsUpdate=!0,Bs(R,X,K),R.side=Dt):Bs(R,X,K)}this.compile=function(R,X,K=null){K===null&&(K=R),p=Ze.get(K),p.init(X),_.push(p),K.traverseVisible(function(Y){Y.isLight&&Y.layers.test(X.layers)&&(p.pushLight(Y),Y.castShadow&&p.pushShadow(Y))}),R!==K&&R.traverseVisible(function(Y){Y.isLight&&Y.layers.test(X.layers)&&(p.pushLight(Y),Y.castShadow&&p.pushShadow(Y))}),p.setupLights();const J=new Set;return R.traverse(function(Y){if(!(Y.isMesh||Y.isPoints||Y.isLine||Y.isSprite))return;const fe=Y.material;if(fe)if(Array.isArray(fe))for(let ye=0;ye<fe.length;ye++){const Ee=fe[ye];tt(Ee,K,Y),J.add(Ee)}else tt(fe,K,Y),J.add(fe)}),_.pop(),p=null,J},this.compileAsync=function(R,X,K=null){const J=this.compile(R,X,K);return new Promise(Y=>{function fe(){if(J.forEach(function(ye){pe.get(ye).currentProgram.isReady()&&J.delete(ye)}),J.size===0){Y(R);return}setTimeout(fe,10)}ae.get("KHR_parallel_shader_compile")!==null?fe():setTimeout(fe,10)})};let Kt=null;function Cn(R){Kt&&Kt(R)}function gl(){ii.stop()}function vl(){ii.start()}const ii=new Fh;ii.setAnimationLoop(Cn),typeof self<"u"&&ii.setContext(self),this.setAnimationLoop=function(R){Kt=R,ee.setAnimationLoop(R),R===null?ii.stop():ii.start()},ee.addEventListener("sessionstart",gl),ee.addEventListener("sessionend",vl),this.render=function(R,X){if(X!==void 0&&X.isCamera!==!0){console.error("THREE.WebGLRenderer.render: camera is not an instance of THREE.Camera.");return}if(M===!0)return;if(R.matrixWorldAutoUpdate===!0&&R.updateMatrixWorld(),X.parent===null&&X.matrixWorldAutoUpdate===!0&&X.updateMatrixWorld(),ee.enabled===!0&&ee.isPresenting===!0&&(ee.cameraAutoUpdate===!0&&ee.updateCamera(X),X=ee.getCamera()),R.isScene===!0&&R.onBeforeRender(v,R,X,C),p=Ze.get(R,_.length),p.init(X),_.push(p),he.multiplyMatrices(X.projectionMatrix,X.matrixWorldInverse),Z.setFromProjectionMatrix(he),$=this.localClippingEnabled,W=ue.init(this.clippingPlanes,$),x=we.get(R,m.length),x.init(),m.push(x),ee.enabled===!0&&ee.isPresenting===!0){const fe=v.xr.getDepthSensingMesh();fe!==null&&eo(fe,X,-1/0,v.sortObjects)}eo(R,X,0,v.sortObjects),x.finish(),v.sortObjects===!0&&x.sort(U,V),ze=ee.enabled===!1||ee.isPresenting===!1||ee.hasDepthSensing()===!1,ze&&Ve.addToRenderList(x,R),this.info.render.frame++,W===!0&&ue.beginShadows();const K=p.state.shadowsArray;Se.render(K,R,X),W===!0&&ue.endShadows(),this.info.autoReset===!0&&this.info.reset();const J=x.opaque,Y=x.transmissive;if(p.setupLights(),X.isArrayCamera){const fe=X.cameras;if(Y.length>0)for(let ye=0,Ee=fe.length;ye<Ee;ye++){const Re=fe[ye];_l(J,Y,R,Re)}ze&&Ve.render(R);for(let ye=0,Ee=fe.length;ye<Ee;ye++){const Re=fe[ye];xl(x,R,Re,Re.viewport)}}else Y.length>0&&_l(J,Y,R,X),ze&&Ve.render(R),xl(x,R,X);C!==null&&(F.updateMultisampleRenderTarget(C),F.updateRenderTargetMipmap(C)),R.isScene===!0&&R.onAfterRender(v,R,X),ht.resetDefaultState(),z=-1,T=null,_.pop(),_.length>0?(p=_[_.length-1],W===!0&&ue.setGlobalState(v.clippingPlanes,p.state.camera)):p=null,m.pop(),m.length>0?x=m[m.length-1]:x=null};function eo(R,X,K,J){if(R.visible===!1)return;if(R.layers.test(X.layers)){if(R.isGroup)K=R.renderOrder;else if(R.isLOD)R.autoUpdate===!0&&R.update(X);else if(R.isLight)p.pushLight(R),R.castShadow&&p.pushShadow(R);else if(R.isSprite){if(!R.frustumCulled||Z.intersectsSprite(R)){J&&Oe.setFromMatrixPosition(R.matrixWorld).applyMatrix4(he);const ye=ie.update(R),Ee=R.material;Ee.visible&&x.push(R,ye,Ee,K,Oe.z,null)}}else if((R.isMesh||R.isLine||R.isPoints)&&(!R.frustumCulled||Z.intersectsObject(R))){const ye=ie.update(R),Ee=R.material;if(J&&(R.boundingSphere!==void 0?(R.boundingSphere===null&&R.computeBoundingSphere(),Oe.copy(R.boundingSphere.center)):(ye.boundingSphere===null&&ye.computeBoundingSphere(),Oe.copy(ye.boundingSphere.center)),Oe.applyMatrix4(R.matrixWorld).applyMatrix4(he)),Array.isArray(Ee)){const Re=ye.groups;for(let ke=0,Be=Re.length;ke<Be;ke++){const Le=Re[ke],rt=Ee[Le.materialIndex];rt&&rt.visible&&x.push(R,ye,rt,K,Oe.z,Le)}}else Ee.visible&&x.push(R,ye,Ee,K,Oe.z,null)}}const fe=R.children;for(let ye=0,Ee=fe.length;ye<Ee;ye++)eo(fe[ye],X,K,J)}function xl(R,X,K,J){const Y=R.opaque,fe=R.transmissive,ye=R.transparent;p.setupLightsView(K),W===!0&&ue.setGlobalState(v.clippingPlanes,K),J&&de.viewport(y.copy(J)),Y.length>0&&ks(Y,X,K),fe.length>0&&ks(fe,X,K),ye.length>0&&ks(ye,X,K),de.buffers.depth.setTest(!0),de.buffers.depth.setMask(!0),de.buffers.color.setMask(!0),de.setPolygonOffset(!1)}function _l(R,X,K,J){if((K.isScene===!0?K.overrideMaterial:null)!==null)return;p.state.transmissionRenderTarget[J.id]===void 0&&(p.state.transmissionRenderTarget[J.id]=new un(1,1,{generateMipmaps:!0,type:ae.has("EXT_color_buffer_half_float")||ae.has("EXT_color_buffer_float")?bn:Vn,minFilter:pi,samples:4,stencilBuffer:r,resolveDepthBuffer:!1,resolveStencilBuffer:!1,colorSpace:nt.workingColorSpace}));const fe=p.state.transmissionRenderTarget[J.id],ye=J.viewport||y;fe.setSize(ye.z,ye.w);const Ee=v.getRenderTarget();v.setRenderTarget(fe),v.getClearColor(L),N=v.getClearAlpha(),N<1&&v.setClearColor(16777215,.5),v.clear(),ze&&Ve.render(K);const Re=v.toneMapping;v.toneMapping=ei;const ke=J.viewport;if(J.viewport!==void 0&&(J.viewport=void 0),p.setupLightsView(J),W===!0&&ue.setGlobalState(v.clippingPlanes,J),ks(R,K,J),F.updateMultisampleRenderTarget(fe),F.updateRenderTargetMipmap(fe),ae.has("WEBGL_multisampled_render_to_texture")===!1){let Be=!1;for(let Le=0,rt=X.length;Le<rt;Le++){const pt=X[Le],bt=pt.object,Qt=pt.geometry,it=pt.material,Ue=pt.group;if(it.side===Dt&&bt.layers.test(J.layers)){const zt=it.side;it.side=Ht,it.needsUpdate=!0,yl(bt,K,J,Qt,it,Ue),it.side=zt,it.needsUpdate=!0,Be=!0}}Be===!0&&(F.updateMultisampleRenderTarget(fe),F.updateRenderTargetMipmap(fe))}v.setRenderTarget(Ee),v.setClearColor(L,N),ke!==void 0&&(J.viewport=ke),v.toneMapping=Re}function ks(R,X,K){const J=X.isScene===!0?X.overrideMaterial:null;for(let Y=0,fe=R.length;Y<fe;Y++){const ye=R[Y],Ee=ye.object,Re=ye.geometry,ke=J===null?ye.material:J,Be=ye.group;Ee.layers.test(K.layers)&&yl(Ee,X,K,Re,ke,Be)}}function yl(R,X,K,J,Y,fe){R.onBeforeRender(v,X,K,J,Y,fe),R.modelViewMatrix.multiplyMatrices(K.matrixWorldInverse,R.matrixWorld),R.normalMatrix.getNormalMatrix(R.modelViewMatrix),Y.onBeforeRender(v,X,K,J,R,fe),Y.transparent===!0&&Y.side===Dt&&Y.forceSinglePass===!1?(Y.side=Ht,Y.needsUpdate=!0,v.renderBufferDirect(K,X,J,Y,R,fe),Y.side=wn,Y.needsUpdate=!0,v.renderBufferDirect(K,X,J,Y,R,fe),Y.side=Dt):v.renderBufferDirect(K,X,J,Y,R,fe),R.onAfterRender(v,X,K,J,Y,fe)}function Bs(R,X,K){X.isScene!==!0&&(X=Ie);const J=pe.get(R),Y=p.state.lights,fe=p.state.shadowsArray,ye=Y.state.version,Ee=Pe.getParameters(R,Y.state,fe,X,K),Re=Pe.getProgramCacheKey(Ee);let ke=J.programs;J.environment=R.isMeshStandardMaterial?X.environment:null,J.fog=X.fog,J.envMap=(R.isMeshStandardMaterial?j:A).get(R.envMap||J.environment),J.envMapRotation=J.environment!==null&&R.envMap===null?X.environmentRotation:R.envMapRotation,ke===void 0&&(R.addEventListener("dispose",Qe),ke=new Map,J.programs=ke);let Be=ke.get(Re);if(Be!==void 0){if(J.currentProgram===Be&&J.lightsStateVersion===ye)return bl(R,Ee),Be}else Ee.uniforms=Pe.getUniforms(R),R.onBeforeCompile(Ee,v),Be=Pe.acquireProgram(Ee,Re),ke.set(Re,Be),J.uniforms=Ee.uniforms;const Le=J.uniforms;return(!R.isShaderMaterial&&!R.isRawShaderMaterial||R.clipping===!0)&&(Le.clippingPlanes=ue.uniform),bl(R,Ee),J.needsLights=mu(R),J.lightsStateVersion=ye,J.needsLights&&(Le.ambientLightColor.value=Y.state.ambient,Le.lightProbe.value=Y.state.probe,Le.directionalLights.value=Y.state.directional,Le.directionalLightShadows.value=Y.state.directionalShadow,Le.spotLights.value=Y.state.spot,Le.spotLightShadows.value=Y.state.spotShadow,Le.rectAreaLights.value=Y.state.rectArea,Le.ltc_1.value=Y.state.rectAreaLTC1,Le.ltc_2.value=Y.state.rectAreaLTC2,Le.pointLights.value=Y.state.point,Le.pointLightShadows.value=Y.state.pointShadow,Le.hemisphereLights.value=Y.state.hemi,Le.directionalShadowMap.value=Y.state.directionalShadowMap,Le.directionalShadowMatrix.value=Y.state.directionalShadowMatrix,Le.spotShadowMap.value=Y.state.spotShadowMap,Le.spotLightMatrix.value=Y.state.spotLightMatrix,Le.spotLightMap.value=Y.state.spotLightMap,Le.pointShadowMap.value=Y.state.pointShadowMap,Le.pointShadowMatrix.value=Y.state.pointShadowMatrix),J.currentProgram=Be,J.uniformsList=null,Be}function Ml(R){if(R.uniformsList===null){const X=R.currentProgram.getUniforms();R.uniformsList=Pr.seqWithValue(X.seq,R.uniforms)}return R.uniformsList}function bl(R,X){const K=pe.get(R);K.outputColorSpace=X.outputColorSpace,K.batching=X.batching,K.batchingColor=X.batchingColor,K.instancing=X.instancing,K.instancingColor=X.instancingColor,K.instancingMorph=X.instancingMorph,K.skinning=X.skinning,K.morphTargets=X.morphTargets,K.morphNormals=X.morphNormals,K.morphColors=X.morphColors,K.morphTargetsCount=X.morphTargetsCount,K.numClippingPlanes=X.numClippingPlanes,K.numIntersection=X.numClipIntersection,K.vertexAlphas=X.vertexAlphas,K.vertexTangents=X.vertexTangents,K.toneMapping=X.toneMapping}function fu(R,X,K,J,Y){X.isScene!==!0&&(X=Ie),F.resetTextureUnits();const fe=X.fog,ye=J.isMeshStandardMaterial?X.environment:null,Ee=C===null?v.outputColorSpace:C.isXRRenderTarget===!0?C.texture.colorSpace:Hn,Re=(J.isMeshStandardMaterial?j:A).get(J.envMap||ye),ke=J.vertexColors===!0&&!!K.attributes.color&&K.attributes.color.itemSize===4,Be=!!K.attributes.tangent&&(!!J.normalMap||J.anisotropy>0),Le=!!K.morphAttributes.position,rt=!!K.morphAttributes.normal,pt=!!K.morphAttributes.color;let bt=ei;J.toneMapped&&(C===null||C.isXRRenderTarget===!0)&&(bt=v.toneMapping);const Qt=K.morphAttributes.position||K.morphAttributes.normal||K.morphAttributes.color,it=Qt!==void 0?Qt.length:0,Ue=pe.get(J),zt=p.state.lights;if(W===!0&&($===!0||R!==T)){const rn=R===T&&J.id===z;ue.setState(J,R,rn)}let st=!1;J.version===Ue.__version?(Ue.needsLights&&Ue.lightsStateVersion!==zt.state.version||Ue.outputColorSpace!==Ee||Y.isBatchedMesh&&Ue.batching===!1||!Y.isBatchedMesh&&Ue.batching===!0||Y.isBatchedMesh&&Ue.batchingColor===!0&&Y.colorTexture===null||Y.isBatchedMesh&&Ue.batchingColor===!1&&Y.colorTexture!==null||Y.isInstancedMesh&&Ue.instancing===!1||!Y.isInstancedMesh&&Ue.instancing===!0||Y.isSkinnedMesh&&Ue.skinning===!1||!Y.isSkinnedMesh&&Ue.skinning===!0||Y.isInstancedMesh&&Ue.instancingColor===!0&&Y.instanceColor===null||Y.isInstancedMesh&&Ue.instancingColor===!1&&Y.instanceColor!==null||Y.isInstancedMesh&&Ue.instancingMorph===!0&&Y.morphTexture===null||Y.isInstancedMesh&&Ue.instancingMorph===!1&&Y.morphTexture!==null||Ue.envMap!==Re||J.fog===!0&&Ue.fog!==fe||Ue.numClippingPlanes!==void 0&&(Ue.numClippingPlanes!==ue.numPlanes||Ue.numIntersection!==ue.numIntersection)||Ue.vertexAlphas!==ke||Ue.vertexTangents!==Be||Ue.morphTargets!==Le||Ue.morphNormals!==rt||Ue.morphColors!==pt||Ue.toneMapping!==bt||Ue.morphTargetsCount!==it)&&(st=!0):(st=!0,Ue.__version=J.version);let dn=Ue.currentProgram;st===!0&&(dn=Bs(J,X,Y));let Ti=!1,en=!1,to=!1;const St=dn.getUniforms(),Gn=Ue.uniforms;if(de.useProgram(dn.program)&&(Ti=!0,en=!0,to=!0),J.id!==z&&(z=J.id,en=!0),Ti||T!==R){se.reverseDepthBuffer?(le.copy(R.projectionMatrix),Sd(le),Td(le),St.setValue(I,"projectionMatrix",le)):St.setValue(I,"projectionMatrix",R.projectionMatrix),St.setValue(I,"viewMatrix",R.matrixWorldInverse);const rn=St.map.cameraPosition;rn!==void 0&&rn.setValue(I,Ce.setFromMatrixPosition(R.matrixWorld)),se.logarithmicDepthBuffer&&St.setValue(I,"logDepthBufFC",2/(Math.log(R.far+1)/Math.LN2)),(J.isMeshPhongMaterial||J.isMeshToonMaterial||J.isMeshLambertMaterial||J.isMeshBasicMaterial||J.isMeshStandardMaterial||J.isShaderMaterial)&&St.setValue(I,"isOrthographic",R.isOrthographicCamera===!0),T!==R&&(T=R,en=!0,to=!0)}if(Y.isSkinnedMesh){St.setOptional(I,Y,"bindMatrix"),St.setOptional(I,Y,"bindMatrixInverse");const rn=Y.skeleton;rn&&(rn.boneTexture===null&&rn.computeBoneTexture(),St.setValue(I,"boneTexture",rn.boneTexture,F))}Y.isBatchedMesh&&(St.setOptional(I,Y,"batchingTexture"),St.setValue(I,"batchingTexture",Y._matricesTexture,F),St.setOptional(I,Y,"batchingIdTexture"),St.setValue(I,"batchingIdTexture",Y._indirectTexture,F),St.setOptional(I,Y,"batchingColorTexture"),Y._colorsTexture!==null&&St.setValue(I,"batchingColorTexture",Y._colorsTexture,F));const no=K.morphAttributes;if((no.position!==void 0||no.normal!==void 0||no.color!==void 0)&&He.update(Y,K,dn),(en||Ue.receiveShadow!==Y.receiveShadow)&&(Ue.receiveShadow=Y.receiveShadow,St.setValue(I,"receiveShadow",Y.receiveShadow)),J.isMeshGouraudMaterial&&J.envMap!==null&&(Gn.envMap.value=Re,Gn.flipEnvMap.value=Re.isCubeTexture&&Re.isRenderTargetTexture===!1?-1:1),J.isMeshStandardMaterial&&J.envMap===null&&X.environment!==null&&(Gn.envMapIntensity.value=X.environmentIntensity),en&&(St.setValue(I,"toneMappingExposure",v.toneMappingExposure),Ue.needsLights&&pu(Gn,to),fe&&J.fog===!0&&me.refreshFogUniforms(Gn,fe),me.refreshMaterialUniforms(Gn,J,q,k,p.state.transmissionRenderTarget[R.id]),Pr.upload(I,Ml(Ue),Gn,F)),J.isShaderMaterial&&J.uniformsNeedUpdate===!0&&(Pr.upload(I,Ml(Ue),Gn,F),J.uniformsNeedUpdate=!1),J.isSpriteMaterial&&St.setValue(I,"center",Y.center),St.setValue(I,"modelViewMatrix",Y.modelViewMatrix),St.setValue(I,"normalMatrix",Y.normalMatrix),St.setValue(I,"modelMatrix",Y.matrixWorld),J.isShaderMaterial||J.isRawShaderMaterial){const rn=J.uniformsGroups;for(let io=0,gu=rn.length;io<gu;io++){const wl=rn[io];G.update(wl,dn),G.bind(wl,dn)}}return dn}function pu(R,X){R.ambientLightColor.needsUpdate=X,R.lightProbe.needsUpdate=X,R.directionalLights.needsUpdate=X,R.directionalLightShadows.needsUpdate=X,R.pointLights.needsUpdate=X,R.pointLightShadows.needsUpdate=X,R.spotLights.needsUpdate=X,R.spotLightShadows.needsUpdate=X,R.rectAreaLights.needsUpdate=X,R.hemisphereLights.needsUpdate=X}function mu(R){return R.isMeshLambertMaterial||R.isMeshToonMaterial||R.isMeshPhongMaterial||R.isMeshStandardMaterial||R.isShadowMaterial||R.isShaderMaterial&&R.lights===!0}this.getActiveCubeFace=function(){return S},this.getActiveMipmapLevel=function(){return E},this.getRenderTarget=function(){return C},this.setRenderTargetTextures=function(R,X,K){pe.get(R.texture).__webglTexture=X,pe.get(R.depthTexture).__webglTexture=K;const J=pe.get(R);J.__hasExternalTextures=!0,J.__autoAllocateDepthBuffer=K===void 0,J.__autoAllocateDepthBuffer||ae.has("WEBGL_multisampled_render_to_texture")===!0&&(console.warn("THREE.WebGLRenderer: Render-to-texture extension was disabled because an external texture was provided"),J.__useRenderToTexture=!1)},this.setRenderTargetFramebuffer=function(R,X){const K=pe.get(R);K.__webglFramebuffer=X,K.__useDefaultFramebuffer=X===void 0},this.setRenderTarget=function(R,X=0,K=0){C=R,S=X,E=K;let J=!0,Y=null,fe=!1,ye=!1;if(R){const Re=pe.get(R);if(Re.__useDefaultFramebuffer!==void 0)de.bindFramebuffer(I.FRAMEBUFFER,null),J=!1;else if(Re.__webglFramebuffer===void 0)F.setupRenderTarget(R);else if(Re.__hasExternalTextures)F.rebindTextures(R,pe.get(R.texture).__webglTexture,pe.get(R.depthTexture).__webglTexture);else if(R.depthBuffer){const Le=R.depthTexture;if(Re.__boundDepthTexture!==Le){if(Le!==null&&pe.has(Le)&&(R.width!==Le.image.width||R.height!==Le.image.height))throw new Error("WebGLRenderTarget: Attached DepthTexture is initialized to the incorrect size.");F.setupDepthRenderbuffer(R)}}const ke=R.texture;(ke.isData3DTexture||ke.isDataArrayTexture||ke.isCompressedArrayTexture)&&(ye=!0);const Be=pe.get(R).__webglFramebuffer;R.isWebGLCubeRenderTarget?(Array.isArray(Be[X])?Y=Be[X][K]:Y=Be[X],fe=!0):R.samples>0&&F.useMultisampledRTT(R)===!1?Y=pe.get(R).__webglMultisampledFramebuffer:Array.isArray(Be)?Y=Be[K]:Y=Be,y.copy(R.viewport),b.copy(R.scissor),D=R.scissorTest}else y.copy(P).multiplyScalar(q).floor(),b.copy(O).multiplyScalar(q).floor(),D=H;if(de.bindFramebuffer(I.FRAMEBUFFER,Y)&&J&&de.drawBuffers(R,Y),de.viewport(y),de.scissor(b),de.setScissorTest(D),fe){const Re=pe.get(R.texture);I.framebufferTexture2D(I.FRAMEBUFFER,I.COLOR_ATTACHMENT0,I.TEXTURE_CUBE_MAP_POSITIVE_X+X,Re.__webglTexture,K)}else if(ye){const Re=pe.get(R.texture),ke=X||0;I.framebufferTextureLayer(I.FRAMEBUFFER,I.COLOR_ATTACHMENT0,Re.__webglTexture,K||0,ke)}z=-1},this.readRenderTargetPixels=function(R,X,K,J,Y,fe,ye){if(!(R&&R.isWebGLRenderTarget)){console.error("THREE.WebGLRenderer.readRenderTargetPixels: renderTarget is not THREE.WebGLRenderTarget.");return}let Ee=pe.get(R).__webglFramebuffer;if(R.isWebGLCubeRenderTarget&&ye!==void 0&&(Ee=Ee[ye]),Ee){de.bindFramebuffer(I.FRAMEBUFFER,Ee);try{const Re=R.texture,ke=Re.format,Be=Re.type;if(!se.textureFormatReadable(ke)){console.error("THREE.WebGLRenderer.readRenderTargetPixels: renderTarget is not in RGBA or implementation defined format.");return}if(!se.textureTypeReadable(Be)){console.error("THREE.WebGLRenderer.readRenderTargetPixels: renderTarget is not in UnsignedByteType or implementation defined type.");return}X>=0&&X<=R.width-J&&K>=0&&K<=R.height-Y&&I.readPixels(X,K,J,Y,We.convert(ke),We.convert(Be),fe)}finally{const Re=C!==null?pe.get(C).__webglFramebuffer:null;de.bindFramebuffer(I.FRAMEBUFFER,Re)}}},this.readRenderTargetPixelsAsync=async function(R,X,K,J,Y,fe,ye){if(!(R&&R.isWebGLRenderTarget))throw new Error("THREE.WebGLRenderer.readRenderTargetPixels: renderTarget is not THREE.WebGLRenderTarget.");let Ee=pe.get(R).__webglFramebuffer;if(R.isWebGLCubeRenderTarget&&ye!==void 0&&(Ee=Ee[ye]),Ee){const Re=R.texture,ke=Re.format,Be=Re.type;if(!se.textureFormatReadable(ke))throw new Error("THREE.WebGLRenderer.readRenderTargetPixelsAsync: renderTarget is not in RGBA or implementation defined format.");if(!se.textureTypeReadable(Be))throw new Error("THREE.WebGLRenderer.readRenderTargetPixelsAsync: renderTarget is not in UnsignedByteType or implementation defined type.");if(X>=0&&X<=R.width-J&&K>=0&&K<=R.height-Y){de.bindFramebuffer(I.FRAMEBUFFER,Ee);const Le=I.createBuffer();I.bindBuffer(I.PIXEL_PACK_BUFFER,Le),I.bufferData(I.PIXEL_PACK_BUFFER,fe.byteLength,I.STREAM_READ),I.readPixels(X,K,J,Y,We.convert(ke),We.convert(Be),0);const rt=C!==null?pe.get(C).__webglFramebuffer:null;de.bindFramebuffer(I.FRAMEBUFFER,rt);const pt=I.fenceSync(I.SYNC_GPU_COMMANDS_COMPLETE,0);return I.flush(),await wd(I,pt,4),I.bindBuffer(I.PIXEL_PACK_BUFFER,Le),I.getBufferSubData(I.PIXEL_PACK_BUFFER,0,fe),I.deleteBuffer(Le),I.deleteSync(pt),fe}else throw new Error("THREE.WebGLRenderer.readRenderTargetPixelsAsync: requested read bounds are out of range.")}},this.copyFramebufferToTexture=function(R,X=null,K=0){R.isTexture!==!0&&(Cr("WebGLRenderer: copyFramebufferToTexture function signature has changed."),X=arguments[0]||null,R=arguments[1]);const J=Math.pow(2,-K),Y=Math.floor(R.image.width*J),fe=Math.floor(R.image.height*J),ye=X!==null?X.x:0,Ee=X!==null?X.y:0;F.setTexture2D(R,0),I.copyTexSubImage2D(I.TEXTURE_2D,K,0,0,ye,Ee,Y,fe),de.unbindTexture()},this.copyTextureToTexture=function(R,X,K=null,J=null,Y=0){R.isTexture!==!0&&(Cr("WebGLRenderer: copyTextureToTexture function signature has changed."),J=arguments[0]||null,R=arguments[1],X=arguments[2],Y=arguments[3]||0,K=null);let fe,ye,Ee,Re,ke,Be;K!==null?(fe=K.max.x-K.min.x,ye=K.max.y-K.min.y,Ee=K.min.x,Re=K.min.y):(fe=R.image.width,ye=R.image.height,Ee=0,Re=0),J!==null?(ke=J.x,Be=J.y):(ke=0,Be=0);const Le=We.convert(X.format),rt=We.convert(X.type);F.setTexture2D(X,0),I.pixelStorei(I.UNPACK_FLIP_Y_WEBGL,X.flipY),I.pixelStorei(I.UNPACK_PREMULTIPLY_ALPHA_WEBGL,X.premultiplyAlpha),I.pixelStorei(I.UNPACK_ALIGNMENT,X.unpackAlignment);const pt=I.getParameter(I.UNPACK_ROW_LENGTH),bt=I.getParameter(I.UNPACK_IMAGE_HEIGHT),Qt=I.getParameter(I.UNPACK_SKIP_PIXELS),it=I.getParameter(I.UNPACK_SKIP_ROWS),Ue=I.getParameter(I.UNPACK_SKIP_IMAGES),zt=R.isCompressedTexture?R.mipmaps[Y]:R.image;I.pixelStorei(I.UNPACK_ROW_LENGTH,zt.width),I.pixelStorei(I.UNPACK_IMAGE_HEIGHT,zt.height),I.pixelStorei(I.UNPACK_SKIP_PIXELS,Ee),I.pixelStorei(I.UNPACK_SKIP_ROWS,Re),R.isDataTexture?I.texSubImage2D(I.TEXTURE_2D,Y,ke,Be,fe,ye,Le,rt,zt.data):R.isCompressedTexture?I.compressedTexSubImage2D(I.TEXTURE_2D,Y,ke,Be,zt.width,zt.height,Le,zt.data):I.texSubImage2D(I.TEXTURE_2D,Y,ke,Be,fe,ye,Le,rt,zt),I.pixelStorei(I.UNPACK_ROW_LENGTH,pt),I.pixelStorei(I.UNPACK_IMAGE_HEIGHT,bt),I.pixelStorei(I.UNPACK_SKIP_PIXELS,Qt),I.pixelStorei(I.UNPACK_SKIP_ROWS,it),I.pixelStorei(I.UNPACK_SKIP_IMAGES,Ue),Y===0&&X.generateMipmaps&&I.generateMipmap(I.TEXTURE_2D),de.unbindTexture()},this.copyTextureToTexture3D=function(R,X,K=null,J=null,Y=0){R.isTexture!==!0&&(Cr("WebGLRenderer: copyTextureToTexture3D function signature has changed."),K=arguments[0]||null,J=arguments[1]||null,R=arguments[2],X=arguments[3],Y=arguments[4]||0);let fe,ye,Ee,Re,ke,Be,Le,rt,pt;const bt=R.isCompressedTexture?R.mipmaps[Y]:R.image;K!==null?(fe=K.max.x-K.min.x,ye=K.max.y-K.min.y,Ee=K.max.z-K.min.z,Re=K.min.x,ke=K.min.y,Be=K.min.z):(fe=bt.width,ye=bt.height,Ee=bt.depth,Re=0,ke=0,Be=0),J!==null?(Le=J.x,rt=J.y,pt=J.z):(Le=0,rt=0,pt=0);const Qt=We.convert(X.format),it=We.convert(X.type);let Ue;if(X.isData3DTexture)F.setTexture3D(X,0),Ue=I.TEXTURE_3D;else if(X.isDataArrayTexture||X.isCompressedArrayTexture)F.setTexture2DArray(X,0),Ue=I.TEXTURE_2D_ARRAY;else{console.warn("THREE.WebGLRenderer.copyTextureToTexture3D: only supports THREE.DataTexture3D and THREE.DataTexture2DArray.");return}I.pixelStorei(I.UNPACK_FLIP_Y_WEBGL,X.flipY),I.pixelStorei(I.UNPACK_PREMULTIPLY_ALPHA_WEBGL,X.premultiplyAlpha),I.pixelStorei(I.UNPACK_ALIGNMENT,X.unpackAlignment);const zt=I.getParameter(I.UNPACK_ROW_LENGTH),st=I.getParameter(I.UNPACK_IMAGE_HEIGHT),dn=I.getParameter(I.UNPACK_SKIP_PIXELS),Ti=I.getParameter(I.UNPACK_SKIP_ROWS),en=I.getParameter(I.UNPACK_SKIP_IMAGES);I.pixelStorei(I.UNPACK_ROW_LENGTH,bt.width),I.pixelStorei(I.UNPACK_IMAGE_HEIGHT,bt.height),I.pixelStorei(I.UNPACK_SKIP_PIXELS,Re),I.pixelStorei(I.UNPACK_SKIP_ROWS,ke),I.pixelStorei(I.UNPACK_SKIP_IMAGES,Be),R.isDataTexture||R.isData3DTexture?I.texSubImage3D(Ue,Y,Le,rt,pt,fe,ye,Ee,Qt,it,bt.data):X.isCompressedArrayTexture?I.compressedTexSubImage3D(Ue,Y,Le,rt,pt,fe,ye,Ee,Qt,bt.data):I.texSubImage3D(Ue,Y,Le,rt,pt,fe,ye,Ee,Qt,it,bt),I.pixelStorei(I.UNPACK_ROW_LENGTH,zt),I.pixelStorei(I.UNPACK_IMAGE_HEIGHT,st),I.pixelStorei(I.UNPACK_SKIP_PIXELS,dn),I.pixelStorei(I.UNPACK_SKIP_ROWS,Ti),I.pixelStorei(I.UNPACK_SKIP_IMAGES,en),Y===0&&X.generateMipmaps&&I.generateMipmap(Ue),de.unbindTexture()},this.initRenderTarget=function(R){pe.get(R).__webglFramebuffer===void 0&&F.setupRenderTarget(R)},this.initTexture=function(R){R.isCubeTexture?F.setTextureCube(R,0):R.isData3DTexture?F.setTexture3D(R,0):R.isDataArrayTexture||R.isCompressedArrayTexture?F.setTexture2DArray(R,0):F.setTexture2D(R,0),de.unbindTexture()},this.resetState=function(){S=0,E=0,C=null,de.reset(),ht.reset()},typeof __THREE_DEVTOOLS__<"u"&&__THREE_DEVTOOLS__.dispatchEvent(new CustomEvent("observe",{detail:this}))}get coordinateSystem(){return zn}get outputColorSpace(){return this._outputColorSpace}set outputColorSpace(e){this._outputColorSpace=e;const t=this.getContext();t.drawingBufferColorSpace=e===Ja?"display-p3":"srgb",t.unpackColorSpace=nt.workingColorSpace===Yr?"display-p3":"srgb"}}class kg extends Mt{constructor(){super(),this.isScene=!0,this.type="Scene",this.background=null,this.environment=null,this.fog=null,this.backgroundBlurriness=0,this.backgroundIntensity=1,this.backgroundRotation=new Yt,this.environmentIntensity=1,this.environmentRotation=new Yt,this.overrideMaterial=null,typeof __THREE_DEVTOOLS__<"u"&&__THREE_DEVTOOLS__.dispatchEvent(new CustomEvent("observe",{detail:this}))}copy(e,t){return super.copy(e,t),e.background!==null&&(this.background=e.background.clone()),e.environment!==null&&(this.environment=e.environment.clone()),e.fog!==null&&(this.fog=e.fog.clone()),this.backgroundBlurriness=e.backgroundBlurriness,this.backgroundIntensity=e.backgroundIntensity,this.backgroundRotation.copy(e.backgroundRotation),this.environmentIntensity=e.environmentIntensity,this.environmentRotation.copy(e.environmentRotation),e.overrideMaterial!==null&&(this.overrideMaterial=e.overrideMaterial.clone()),this.matrixAutoUpdate=e.matrixAutoUpdate,this}toJSON(e){const t=super.toJSON(e);return this.fog!==null&&(t.object.fog=this.fog.toJSON()),this.backgroundBlurriness>0&&(t.object.backgroundBlurriness=this.backgroundBlurriness),this.backgroundIntensity!==1&&(t.object.backgroundIntensity=this.backgroundIntensity),t.object.backgroundRotation=this.backgroundRotation.toArray(),this.environmentIntensity!==1&&(t.object.environmentIntensity=this.environmentIntensity),t.object.environmentRotation=this.environmentRotation.toArray(),t}}class Gh extends It{constructor(e=null,t=1,n=1,i,r,o,a,l,c=$t,h=$t,u,d){super(null,o,a,l,c,h,i,r,u,d),this.isDataTexture=!0,this.image={data:e,width:t,height:n},this.generateMipmaps=!1,this.flipY=!1,this.unpackAlignment=1}}class vc extends kt{constructor(e,t,n,i=1){super(e,t,n),this.isInstancedBufferAttribute=!0,this.meshPerAttribute=i}copy(e){return super.copy(e),this.meshPerAttribute=e.meshPerAttribute,this}toJSON(){const e=super.toJSON();return e.meshPerAttribute=this.meshPerAttribute,e.isInstancedBufferAttribute=!0,e}}const Bi=new Fe,xc=new Fe,hr=[],_c=new Lt,Bg=new Fe,gs=new ve,vs=new Mi;class il extends ve{constructor(e,t,n){super(e,t),this.isInstancedMesh=!0,this.instanceMatrix=new vc(new Float32Array(n*16),16),this.instanceColor=null,this.morphTexture=null,this.count=n,this.boundingBox=null,this.boundingSphere=null;for(let i=0;i<n;i++)this.setMatrixAt(i,Bg)}computeBoundingBox(){const e=this.geometry,t=this.count;this.boundingBox===null&&(this.boundingBox=new Lt),e.boundingBox===null&&e.computeBoundingBox(),this.boundingBox.makeEmpty();for(let n=0;n<t;n++)this.getMatrixAt(n,Bi),_c.copy(e.boundingBox).applyMatrix4(Bi),this.boundingBox.union(_c)}computeBoundingSphere(){const e=this.geometry,t=this.count;this.boundingSphere===null&&(this.boundingSphere=new Mi),e.boundingSphere===null&&e.computeBoundingSphere(),this.boundingSphere.makeEmpty();for(let n=0;n<t;n++)this.getMatrixAt(n,Bi),vs.copy(e.boundingSphere).applyMatrix4(Bi),this.boundingSphere.union(vs)}copy(e,t){return super.copy(e,t),this.instanceMatrix.copy(e.instanceMatrix),e.morphTexture!==null&&(this.morphTexture=e.morphTexture.clone()),e.instanceColor!==null&&(this.instanceColor=e.instanceColor.clone()),this.count=e.count,e.boundingBox!==null&&(this.boundingBox=e.boundingBox.clone()),e.boundingSphere!==null&&(this.boundingSphere=e.boundingSphere.clone()),this}getColorAt(e,t){t.fromArray(this.instanceColor.array,e*3)}getMatrixAt(e,t){t.fromArray(this.instanceMatrix.array,e*16)}getMorphAt(e,t){const n=t.morphTargetInfluences,i=this.morphTexture.source.data.data,r=n.length+1,o=e*r+1;for(let a=0;a<n.length;a++)n[a]=i[o+a]}raycast(e,t){const n=this.matrixWorld,i=this.count;if(gs.geometry=this.geometry,gs.material=this.material,gs.material!==void 0&&(this.boundingSphere===null&&this.computeBoundingSphere(),vs.copy(this.boundingSphere),vs.applyMatrix4(n),e.ray.intersectsSphere(vs)!==!1))for(let r=0;r<i;r++){this.getMatrixAt(r,Bi),xc.multiplyMatrices(n,Bi),gs.matrixWorld=xc,gs.raycast(e,hr);for(let o=0,a=hr.length;o<a;o++){const l=hr[o];l.instanceId=r,l.object=this,t.push(l)}hr.length=0}}setColorAt(e,t){this.instanceColor===null&&(this.instanceColor=new vc(new Float32Array(this.instanceMatrix.count*3).fill(1),3)),t.toArray(this.instanceColor.array,e*3)}setMatrixAt(e,t){t.toArray(this.instanceMatrix.array,e*16)}setMorphAt(e,t){const n=t.morphTargetInfluences,i=n.length+1;this.morphTexture===null&&(this.morphTexture=new Gh(new Float32Array(i*this.count),i,this.count,qa,Tn));const r=this.morphTexture.source.data.data;let o=0;for(let c=0;c<n.length;c++)o+=n[c];const a=this.geometry.morphTargetsRelative?1:1-o,l=i*e;r[l]=a,r.set(n,l+1)}updateMorphTargets(){}dispose(){return this.dispatchEvent({type:"dispose"}),this.morphTexture!==null&&(this.morphTexture.dispose(),this.morphTexture=null),this}}class sl extends wi{constructor(e){super(),this.isLineBasicMaterial=!0,this.type="LineBasicMaterial",this.color=new Ne(16777215),this.map=null,this.linewidth=1,this.linecap="round",this.linejoin="round",this.fog=!0,this.setValues(e)}copy(e){return super.copy(e),this.color.copy(e.color),this.map=e.map,this.linewidth=e.linewidth,this.linecap=e.linecap,this.linejoin=e.linejoin,this.fog=e.fog,this}}const Fr=new w,zr=new w,yc=new Fe,xs=new bi,ur=new Mi,No=new w,Mc=new w;class Vg extends Mt{constructor(e=new je,t=new sl){super(),this.isLine=!0,this.type="Line",this.geometry=e,this.material=t,this.updateMorphTargets()}copy(e,t){return super.copy(e,t),this.material=Array.isArray(e.material)?e.material.slice():e.material,this.geometry=e.geometry,this}computeLineDistances(){const e=this.geometry;if(e.index===null){const t=e.attributes.position,n=[0];for(let i=1,r=t.count;i<r;i++)Fr.fromBufferAttribute(t,i-1),zr.fromBufferAttribute(t,i),n[i]=n[i-1],n[i]+=Fr.distanceTo(zr);e.setAttribute("lineDistance",new Ae(n,1))}else console.warn("THREE.Line.computeLineDistances(): Computation only possible with non-indexed BufferGeometry.");return this}raycast(e,t){const n=this.geometry,i=this.matrixWorld,r=e.params.Line.threshold,o=n.drawRange;if(n.boundingSphere===null&&n.computeBoundingSphere(),ur.copy(n.boundingSphere),ur.applyMatrix4(i),ur.radius+=r,e.ray.intersectsSphere(ur)===!1)return;yc.copy(i).invert(),xs.copy(e.ray).applyMatrix4(yc);const a=r/((this.scale.x+this.scale.y+this.scale.z)/3),l=a*a,c=this.isLineSegments?2:1,h=n.index,d=n.attributes.position;if(h!==null){const f=Math.max(0,o.start),g=Math.min(h.count,o.start+o.count);for(let x=f,p=g-1;x<p;x+=c){const m=h.getX(x),_=h.getX(x+1),v=dr(this,e,xs,l,m,_);v&&t.push(v)}if(this.isLineLoop){const x=h.getX(g-1),p=h.getX(f),m=dr(this,e,xs,l,x,p);m&&t.push(m)}}else{const f=Math.max(0,o.start),g=Math.min(d.count,o.start+o.count);for(let x=f,p=g-1;x<p;x+=c){const m=dr(this,e,xs,l,x,x+1);m&&t.push(m)}if(this.isLineLoop){const x=dr(this,e,xs,l,g-1,f);x&&t.push(x)}}}updateMorphTargets(){const t=this.geometry.morphAttributes,n=Object.keys(t);if(n.length>0){const i=t[n[0]];if(i!==void 0){this.morphTargetInfluences=[],this.morphTargetDictionary={};for(let r=0,o=i.length;r<o;r++){const a=i[r].name||String(r);this.morphTargetInfluences.push(0),this.morphTargetDictionary[a]=r}}}}}function dr(s,e,t,n,i,r){const o=s.geometry.attributes.position;if(Fr.fromBufferAttribute(o,i),zr.fromBufferAttribute(o,r),t.distanceSqToSegment(Fr,zr,No,Mc)>n)return;No.applyMatrix4(s.matrixWorld);const l=e.ray.origin.distanceTo(No);if(!(l<e.near||l>e.far))return{distance:l,point:Mc.clone().applyMatrix4(s.matrixWorld),index:i,face:null,faceIndex:null,barycoord:null,object:s}}const bc=new w,wc=new w;class Hg extends Vg{constructor(e,t){super(e,t),this.isLineSegments=!0,this.type="LineSegments"}computeLineDistances(){const e=this.geometry;if(e.index===null){const t=e.attributes.position,n=[];for(let i=0,r=t.count;i<r;i+=2)bc.fromBufferAttribute(t,i),wc.fromBufferAttribute(t,i+1),n[i]=i===0?0:n[i-1],n[i+1]=n[i]+bc.distanceTo(wc);e.setAttribute("lineDistance",new Ae(n,1))}else console.warn("THREE.LineSegments.computeLineDistances(): Computation only possible with non-indexed BufferGeometry.");return this}}class rl extends wi{constructor(e){super(),this.isPointsMaterial=!0,this.type="PointsMaterial",this.color=new Ne(16777215),this.map=null,this.alphaMap=null,this.size=1,this.sizeAttenuation=!0,this.fog=!0,this.setValues(e)}copy(e){return super.copy(e),this.color.copy(e.color),this.map=e.map,this.alphaMap=e.alphaMap,this.size=e.size,this.sizeAttenuation=e.sizeAttenuation,this.fog=e.fog,this}}const Sc=new Fe,Ia=new bi,fr=new Mi,pr=new w;class ol extends Mt{constructor(e=new je,t=new rl){super(),this.isPoints=!0,this.type="Points",this.geometry=e,this.material=t,this.updateMorphTargets()}copy(e,t){return super.copy(e,t),this.material=Array.isArray(e.material)?e.material.slice():e.material,this.geometry=e.geometry,this}raycast(e,t){const n=this.geometry,i=this.matrixWorld,r=e.params.Points.threshold,o=n.drawRange;if(n.boundingSphere===null&&n.computeBoundingSphere(),fr.copy(n.boundingSphere),fr.applyMatrix4(i),fr.radius+=r,e.ray.intersectsSphere(fr)===!1)return;Sc.copy(i).invert(),Ia.copy(e.ray).applyMatrix4(Sc);const a=r/((this.scale.x+this.scale.y+this.scale.z)/3),l=a*a,c=n.index,u=n.attributes.position;if(c!==null){const d=Math.max(0,o.start),f=Math.min(c.count,o.start+o.count);for(let g=d,x=f;g<x;g++){const p=c.getX(g);pr.fromBufferAttribute(u,p),Tc(pr,p,l,i,e,t,this)}}else{const d=Math.max(0,o.start),f=Math.min(u.count,o.start+o.count);for(let g=d,x=f;g<x;g++)pr.fromBufferAttribute(u,g),Tc(pr,g,l,i,e,t,this)}}updateMorphTargets(){const t=this.geometry.morphAttributes,n=Object.keys(t);if(n.length>0){const i=t[n[0]];if(i!==void 0){this.morphTargetInfluences=[],this.morphTargetDictionary={};for(let r=0,o=i.length;r<o;r++){const a=i[r].name||String(r);this.morphTargetInfluences.push(0),this.morphTargetDictionary[a]=r}}}}}function Tc(s,e,t,n,i,r,o){const a=Ia.distanceSqToPoint(s);if(a<t){const l=new w;Ia.closestPointToPoint(s,l),l.applyMatrix4(n);const c=i.ray.origin.distanceTo(l);if(c<i.near||c>i.far)return;r.push({distance:c,distanceToRay:Math.sqrt(a),point:l,index:e,face:null,faceIndex:null,barycoord:null,object:o})}}class ss extends It{constructor(e,t,n,i,r,o,a,l,c){super(e,t,n,i,r,o,a,l,c),this.isCanvasTexture=!0,this.needsUpdate=!0}}class An{constructor(){this.type="Curve",this.arcLengthDivisions=200}getPoint(){return console.warn("THREE.Curve: .getPoint() not implemented."),null}getPointAt(e,t){const n=this.getUtoTmapping(e);return this.getPoint(n,t)}getPoints(e=5){const t=[];for(let n=0;n<=e;n++)t.push(this.getPoint(n/e));return t}getSpacedPoints(e=5){const t=[];for(let n=0;n<=e;n++)t.push(this.getPointAt(n/e));return t}getLength(){const e=this.getLengths();return e[e.length-1]}getLengths(e=this.arcLengthDivisions){if(this.cacheArcLengths&&this.cacheArcLengths.length===e+1&&!this.needsUpdate)return this.cacheArcLengths;this.needsUpdate=!1;const t=[];let n,i=this.getPoint(0),r=0;t.push(0);for(let o=1;o<=e;o++)n=this.getPoint(o/e),r+=n.distanceTo(i),t.push(r),i=n;return this.cacheArcLengths=t,t}updateArcLengths(){this.needsUpdate=!0,this.getLengths()}getUtoTmapping(e,t){const n=this.getLengths();let i=0;const r=n.length;let o;t?o=t:o=e*n[r-1];let a=0,l=r-1,c;for(;a<=l;)if(i=Math.floor(a+(l-a)/2),c=n[i]-o,c<0)a=i+1;else if(c>0)l=i-1;else{l=i;break}if(i=l,n[i]===o)return i/(r-1);const h=n[i],d=n[i+1]-h,f=(o-h)/d;return(i+f)/(r-1)}getTangent(e,t){let i=e-1e-4,r=e+1e-4;i<0&&(i=0),r>1&&(r=1);const o=this.getPoint(i),a=this.getPoint(r),l=t||(o.isVector2?new Q:new w);return l.copy(a).sub(o).normalize(),l}getTangentAt(e,t){const n=this.getUtoTmapping(e);return this.getTangent(n,t)}computeFrenetFrames(e,t){const n=new w,i=[],r=[],o=[],a=new w,l=new Fe;for(let f=0;f<=e;f++){const g=f/e;i[f]=this.getTangentAt(g,new w)}r[0]=new w,o[0]=new w;let c=Number.MAX_VALUE;const h=Math.abs(i[0].x),u=Math.abs(i[0].y),d=Math.abs(i[0].z);h<=c&&(c=h,n.set(1,0,0)),u<=c&&(c=u,n.set(0,1,0)),d<=c&&n.set(0,0,1),a.crossVectors(i[0],n).normalize(),r[0].crossVectors(i[0],a),o[0].crossVectors(i[0],r[0]);for(let f=1;f<=e;f++){if(r[f]=r[f-1].clone(),o[f]=o[f-1].clone(),a.crossVectors(i[f-1],i[f]),a.length()>Number.EPSILON){a.normalize();const g=Math.acos(Tt(i[f-1].dot(i[f]),-1,1));r[f].applyMatrix4(l.makeRotationAxis(a,g))}o[f].crossVectors(i[f],r[f])}if(t===!0){let f=Math.acos(Tt(r[0].dot(r[e]),-1,1));f/=e,i[0].dot(a.crossVectors(r[0],r[e]))>0&&(f=-f);for(let g=1;g<=e;g++)r[g].applyMatrix4(l.makeRotationAxis(i[g],f*g)),o[g].crossVectors(i[g],r[g])}return{tangents:i,normals:r,binormals:o}}clone(){return new this.constructor().copy(this)}copy(e){return this.arcLengthDivisions=e.arcLengthDivisions,this}toJSON(){const e={metadata:{version:4.6,type:"Curve",generator:"Curve.toJSON"}};return e.arcLengthDivisions=this.arcLengthDivisions,e.type=this.type,e}fromJSON(e){return this.arcLengthDivisions=e.arcLengthDivisions,this}}class al extends An{constructor(e=0,t=0,n=1,i=1,r=0,o=Math.PI*2,a=!1,l=0){super(),this.isEllipseCurve=!0,this.type="EllipseCurve",this.aX=e,this.aY=t,this.xRadius=n,this.yRadius=i,this.aStartAngle=r,this.aEndAngle=o,this.aClockwise=a,this.aRotation=l}getPoint(e,t=new Q){const n=t,i=Math.PI*2;let r=this.aEndAngle-this.aStartAngle;const o=Math.abs(r)<Number.EPSILON;for(;r<0;)r+=i;for(;r>i;)r-=i;r<Number.EPSILON&&(o?r=0:r=i),this.aClockwise===!0&&!o&&(r===i?r=-i:r=r-i);const a=this.aStartAngle+e*r;let l=this.aX+this.xRadius*Math.cos(a),c=this.aY+this.yRadius*Math.sin(a);if(this.aRotation!==0){const h=Math.cos(this.aRotation),u=Math.sin(this.aRotation),d=l-this.aX,f=c-this.aY;l=d*h-f*u+this.aX,c=d*u+f*h+this.aY}return n.set(l,c)}copy(e){return super.copy(e),this.aX=e.aX,this.aY=e.aY,this.xRadius=e.xRadius,this.yRadius=e.yRadius,this.aStartAngle=e.aStartAngle,this.aEndAngle=e.aEndAngle,this.aClockwise=e.aClockwise,this.aRotation=e.aRotation,this}toJSON(){const e=super.toJSON();return e.aX=this.aX,e.aY=this.aY,e.xRadius=this.xRadius,e.yRadius=this.yRadius,e.aStartAngle=this.aStartAngle,e.aEndAngle=this.aEndAngle,e.aClockwise=this.aClockwise,e.aRotation=this.aRotation,e}fromJSON(e){return super.fromJSON(e),this.aX=e.aX,this.aY=e.aY,this.xRadius=e.xRadius,this.yRadius=e.yRadius,this.aStartAngle=e.aStartAngle,this.aEndAngle=e.aEndAngle,this.aClockwise=e.aClockwise,this.aRotation=e.aRotation,this}}class Gg extends al{constructor(e,t,n,i,r,o){super(e,t,n,n,i,r,o),this.isArcCurve=!0,this.type="ArcCurve"}}function ll(){let s=0,e=0,t=0,n=0;function i(r,o,a,l){s=r,e=a,t=-3*r+3*o-2*a-l,n=2*r-2*o+a+l}return{initCatmullRom:function(r,o,a,l,c){i(o,a,c*(a-r),c*(l-o))},initNonuniformCatmullRom:function(r,o,a,l,c,h,u){let d=(o-r)/c-(a-r)/(c+h)+(a-o)/h,f=(a-o)/h-(l-o)/(h+u)+(l-a)/u;d*=h,f*=h,i(o,a,d,f)},calc:function(r){const o=r*r,a=o*r;return s+e*r+t*o+n*a}}}const mr=new w,Uo=new ll,Oo=new ll,Fo=new ll;class hn extends An{constructor(e=[],t=!1,n="centripetal",i=.5){super(),this.isCatmullRomCurve3=!0,this.type="CatmullRomCurve3",this.points=e,this.closed=t,this.curveType=n,this.tension=i}getPoint(e,t=new w){const n=t,i=this.points,r=i.length,o=(r-(this.closed?0:1))*e;let a=Math.floor(o),l=o-a;this.closed?a+=a>0?0:(Math.floor(Math.abs(a)/r)+1)*r:l===0&&a===r-1&&(a=r-2,l=1);let c,h;this.closed||a>0?c=i[(a-1)%r]:(mr.subVectors(i[0],i[1]).add(i[0]),c=mr);const u=i[a%r],d=i[(a+1)%r];if(this.closed||a+2<r?h=i[(a+2)%r]:(mr.subVectors(i[r-1],i[r-2]).add(i[r-1]),h=mr),this.curveType==="centripetal"||this.curveType==="chordal"){const f=this.curveType==="chordal"?.5:.25;let g=Math.pow(c.distanceToSquared(u),f),x=Math.pow(u.distanceToSquared(d),f),p=Math.pow(d.distanceToSquared(h),f);x<1e-4&&(x=1),g<1e-4&&(g=x),p<1e-4&&(p=x),Uo.initNonuniformCatmullRom(c.x,u.x,d.x,h.x,g,x,p),Oo.initNonuniformCatmullRom(c.y,u.y,d.y,h.y,g,x,p),Fo.initNonuniformCatmullRom(c.z,u.z,d.z,h.z,g,x,p)}else this.curveType==="catmullrom"&&(Uo.initCatmullRom(c.x,u.x,d.x,h.x,this.tension),Oo.initCatmullRom(c.y,u.y,d.y,h.y,this.tension),Fo.initCatmullRom(c.z,u.z,d.z,h.z,this.tension));return n.set(Uo.calc(l),Oo.calc(l),Fo.calc(l)),n}copy(e){super.copy(e),this.points=[];for(let t=0,n=e.points.length;t<n;t++){const i=e.points[t];this.points.push(i.clone())}return this.closed=e.closed,this.curveType=e.curveType,this.tension=e.tension,this}toJSON(){const e=super.toJSON();e.points=[];for(let t=0,n=this.points.length;t<n;t++){const i=this.points[t];e.points.push(i.toArray())}return e.closed=this.closed,e.curveType=this.curveType,e.tension=this.tension,e}fromJSON(e){super.fromJSON(e),this.points=[];for(let t=0,n=e.points.length;t<n;t++){const i=e.points[t];this.points.push(new w().fromArray(i))}return this.closed=e.closed,this.curveType=e.curveType,this.tension=e.tension,this}}function Ec(s,e,t,n,i){const r=(n-e)*.5,o=(i-t)*.5,a=s*s,l=s*a;return(2*t-2*n+r+o)*l+(-3*t+3*n-2*r-o)*a+r*s+t}function Wg(s,e){const t=1-s;return t*t*e}function Xg(s,e){return 2*(1-s)*s*e}function Yg(s,e){return s*s*e}function Es(s,e,t,n){return Wg(s,e)+Xg(s,t)+Yg(s,n)}function qg(s,e){const t=1-s;return t*t*t*e}function jg(s,e){const t=1-s;return 3*t*t*s*e}function Kg(s,e){return 3*(1-s)*s*s*e}function Zg(s,e){return s*s*s*e}function As(s,e,t,n,i){return qg(s,e)+jg(s,t)+Kg(s,n)+Zg(s,i)}class Wh extends An{constructor(e=new Q,t=new Q,n=new Q,i=new Q){super(),this.isCubicBezierCurve=!0,this.type="CubicBezierCurve",this.v0=e,this.v1=t,this.v2=n,this.v3=i}getPoint(e,t=new Q){const n=t,i=this.v0,r=this.v1,o=this.v2,a=this.v3;return n.set(As(e,i.x,r.x,o.x,a.x),As(e,i.y,r.y,o.y,a.y)),n}copy(e){return super.copy(e),this.v0.copy(e.v0),this.v1.copy(e.v1),this.v2.copy(e.v2),this.v3.copy(e.v3),this}toJSON(){const e=super.toJSON();return e.v0=this.v0.toArray(),e.v1=this.v1.toArray(),e.v2=this.v2.toArray(),e.v3=this.v3.toArray(),e}fromJSON(e){return super.fromJSON(e),this.v0.fromArray(e.v0),this.v1.fromArray(e.v1),this.v2.fromArray(e.v2),this.v3.fromArray(e.v3),this}}class Jg extends An{constructor(e=new w,t=new w,n=new w,i=new w){super(),this.isCubicBezierCurve3=!0,this.type="CubicBezierCurve3",this.v0=e,this.v1=t,this.v2=n,this.v3=i}getPoint(e,t=new w){const n=t,i=this.v0,r=this.v1,o=this.v2,a=this.v3;return n.set(As(e,i.x,r.x,o.x,a.x),As(e,i.y,r.y,o.y,a.y),As(e,i.z,r.z,o.z,a.z)),n}copy(e){return super.copy(e),this.v0.copy(e.v0),this.v1.copy(e.v1),this.v2.copy(e.v2),this.v3.copy(e.v3),this}toJSON(){const e=super.toJSON();return e.v0=this.v0.toArray(),e.v1=this.v1.toArray(),e.v2=this.v2.toArray(),e.v3=this.v3.toArray(),e}fromJSON(e){return super.fromJSON(e),this.v0.fromArray(e.v0),this.v1.fromArray(e.v1),this.v2.fromArray(e.v2),this.v3.fromArray(e.v3),this}}class Xh extends An{constructor(e=new Q,t=new Q){super(),this.isLineCurve=!0,this.type="LineCurve",this.v1=e,this.v2=t}getPoint(e,t=new Q){const n=t;return e===1?n.copy(this.v2):(n.copy(this.v2).sub(this.v1),n.multiplyScalar(e).add(this.v1)),n}getPointAt(e,t){return this.getPoint(e,t)}getTangent(e,t=new Q){return t.subVectors(this.v2,this.v1).normalize()}getTangentAt(e,t){return this.getTangent(e,t)}copy(e){return super.copy(e),this.v1.copy(e.v1),this.v2.copy(e.v2),this}toJSON(){const e=super.toJSON();return e.v1=this.v1.toArray(),e.v2=this.v2.toArray(),e}fromJSON(e){return super.fromJSON(e),this.v1.fromArray(e.v1),this.v2.fromArray(e.v2),this}}class $g extends An{constructor(e=new w,t=new w){super(),this.isLineCurve3=!0,this.type="LineCurve3",this.v1=e,this.v2=t}getPoint(e,t=new w){const n=t;return e===1?n.copy(this.v2):(n.copy(this.v2).sub(this.v1),n.multiplyScalar(e).add(this.v1)),n}getPointAt(e,t){return this.getPoint(e,t)}getTangent(e,t=new w){return t.subVectors(this.v2,this.v1).normalize()}getTangentAt(e,t){return this.getTangent(e,t)}copy(e){return super.copy(e),this.v1.copy(e.v1),this.v2.copy(e.v2),this}toJSON(){const e=super.toJSON();return e.v1=this.v1.toArray(),e.v2=this.v2.toArray(),e}fromJSON(e){return super.fromJSON(e),this.v1.fromArray(e.v1),this.v2.fromArray(e.v2),this}}class Yh extends An{constructor(e=new Q,t=new Q,n=new Q){super(),this.isQuadraticBezierCurve=!0,this.type="QuadraticBezierCurve",this.v0=e,this.v1=t,this.v2=n}getPoint(e,t=new Q){const n=t,i=this.v0,r=this.v1,o=this.v2;return n.set(Es(e,i.x,r.x,o.x),Es(e,i.y,r.y,o.y)),n}copy(e){return super.copy(e),this.v0.copy(e.v0),this.v1.copy(e.v1),this.v2.copy(e.v2),this}toJSON(){const e=super.toJSON();return e.v0=this.v0.toArray(),e.v1=this.v1.toArray(),e.v2=this.v2.toArray(),e}fromJSON(e){return super.fromJSON(e),this.v0.fromArray(e.v0),this.v1.fromArray(e.v1),this.v2.fromArray(e.v2),this}}class qh extends An{constructor(e=new w,t=new w,n=new w){super(),this.isQuadraticBezierCurve3=!0,this.type="QuadraticBezierCurve3",this.v0=e,this.v1=t,this.v2=n}getPoint(e,t=new w){const n=t,i=this.v0,r=this.v1,o=this.v2;return n.set(Es(e,i.x,r.x,o.x),Es(e,i.y,r.y,o.y),Es(e,i.z,r.z,o.z)),n}copy(e){return super.copy(e),this.v0.copy(e.v0),this.v1.copy(e.v1),this.v2.copy(e.v2),this}toJSON(){const e=super.toJSON();return e.v0=this.v0.toArray(),e.v1=this.v1.toArray(),e.v2=this.v2.toArray(),e}fromJSON(e){return super.fromJSON(e),this.v0.fromArray(e.v0),this.v1.fromArray(e.v1),this.v2.fromArray(e.v2),this}}class jh extends An{constructor(e=[]){super(),this.isSplineCurve=!0,this.type="SplineCurve",this.points=e}getPoint(e,t=new Q){const n=t,i=this.points,r=(i.length-1)*e,o=Math.floor(r),a=r-o,l=i[o===0?o:o-1],c=i[o],h=i[o>i.length-2?i.length-1:o+1],u=i[o>i.length-3?i.length-1:o+2];return n.set(Ec(a,l.x,c.x,h.x,u.x),Ec(a,l.y,c.y,h.y,u.y)),n}copy(e){super.copy(e),this.points=[];for(let t=0,n=e.points.length;t<n;t++){const i=e.points[t];this.points.push(i.clone())}return this}toJSON(){const e=super.toJSON();e.points=[];for(let t=0,n=this.points.length;t<n;t++){const i=this.points[t];e.points.push(i.toArray())}return e}fromJSON(e){super.fromJSON(e),this.points=[];for(let t=0,n=e.points.length;t<n;t++){const i=e.points[t];this.points.push(new Q().fromArray(i))}return this}}var kr=Object.freeze({__proto__:null,ArcCurve:Gg,CatmullRomCurve3:hn,CubicBezierCurve:Wh,CubicBezierCurve3:Jg,EllipseCurve:al,LineCurve:Xh,LineCurve3:$g,QuadraticBezierCurve:Yh,QuadraticBezierCurve3:qh,SplineCurve:jh});class Qg extends An{constructor(){super(),this.type="CurvePath",this.curves=[],this.autoClose=!1}add(e){this.curves.push(e)}closePath(){const e=this.curves[0].getPoint(0),t=this.curves[this.curves.length-1].getPoint(1);if(!e.equals(t)){const n=e.isVector2===!0?"LineCurve":"LineCurve3";this.curves.push(new kr[n](t,e))}return this}getPoint(e,t){const n=e*this.getLength(),i=this.getCurveLengths();let r=0;for(;r<i.length;){if(i[r]>=n){const o=i[r]-n,a=this.curves[r],l=a.getLength(),c=l===0?0:1-o/l;return a.getPointAt(c,t)}r++}return null}getLength(){const e=this.getCurveLengths();return e[e.length-1]}updateArcLengths(){this.needsUpdate=!0,this.cacheLengths=null,this.getCurveLengths()}getCurveLengths(){if(this.cacheLengths&&this.cacheLengths.length===this.curves.length)return this.cacheLengths;const e=[];let t=0;for(let n=0,i=this.curves.length;n<i;n++)t+=this.curves[n].getLength(),e.push(t);return this.cacheLengths=e,e}getSpacedPoints(e=40){const t=[];for(let n=0;n<=e;n++)t.push(this.getPoint(n/e));return this.autoClose&&t.push(t[0]),t}getPoints(e=12){const t=[];let n;for(let i=0,r=this.curves;i<r.length;i++){const o=r[i],a=o.isEllipseCurve?e*2:o.isLineCurve||o.isLineCurve3?1:o.isSplineCurve?e*o.points.length:e,l=o.getPoints(a);for(let c=0;c<l.length;c++){const h=l[c];n&&n.equals(h)||(t.push(h),n=h)}}return this.autoClose&&t.length>1&&!t[t.length-1].equals(t[0])&&t.push(t[0]),t}copy(e){super.copy(e),this.curves=[];for(let t=0,n=e.curves.length;t<n;t++){const i=e.curves[t];this.curves.push(i.clone())}return this.autoClose=e.autoClose,this}toJSON(){const e=super.toJSON();e.autoClose=this.autoClose,e.curves=[];for(let t=0,n=this.curves.length;t<n;t++){const i=this.curves[t];e.curves.push(i.toJSON())}return e}fromJSON(e){super.fromJSON(e),this.autoClose=e.autoClose,this.curves=[];for(let t=0,n=e.curves.length;t<n;t++){const i=e.curves[t];this.curves.push(new kr[i.type]().fromJSON(i))}return this}}class vi extends Qg{constructor(e){super(),this.type="Path",this.currentPoint=new Q,e&&this.setFromPoints(e)}setFromPoints(e){this.moveTo(e[0].x,e[0].y);for(let t=1,n=e.length;t<n;t++)this.lineTo(e[t].x,e[t].y);return this}moveTo(e,t){return this.currentPoint.set(e,t),this}lineTo(e,t){const n=new Xh(this.currentPoint.clone(),new Q(e,t));return this.curves.push(n),this.currentPoint.set(e,t),this}quadraticCurveTo(e,t,n,i){const r=new Yh(this.currentPoint.clone(),new Q(e,t),new Q(n,i));return this.curves.push(r),this.currentPoint.set(n,i),this}bezierCurveTo(e,t,n,i,r,o){const a=new Wh(this.currentPoint.clone(),new Q(e,t),new Q(n,i),new Q(r,o));return this.curves.push(a),this.currentPoint.set(r,o),this}splineThru(e){const t=[this.currentPoint.clone()].concat(e),n=new jh(t);return this.curves.push(n),this.currentPoint.copy(e[e.length-1]),this}arc(e,t,n,i,r,o){const a=this.currentPoint.x,l=this.currentPoint.y;return this.absarc(e+a,t+l,n,i,r,o),this}absarc(e,t,n,i,r,o){return this.absellipse(e,t,n,n,i,r,o),this}ellipse(e,t,n,i,r,o,a,l){const c=this.currentPoint.x,h=this.currentPoint.y;return this.absellipse(e+c,t+h,n,i,r,o,a,l),this}absellipse(e,t,n,i,r,o,a,l){const c=new al(e,t,n,i,r,o,a,l);if(this.curves.length>0){const u=c.getPoint(0);u.equals(this.currentPoint)||this.lineTo(u.x,u.y)}this.curves.push(c);const h=c.getPoint(1);return this.currentPoint.copy(h),this}copy(e){return super.copy(e),this.currentPoint.copy(e.currentPoint),this}toJSON(){const e=super.toJSON();return e.currentPoint=this.currentPoint.toArray(),e}fromJSON(e){return super.fromJSON(e),this.currentPoint.fromArray(e.currentPoint),this}}class jr extends je{constructor(e=[new Q(0,-.5),new Q(.5,0),new Q(0,.5)],t=12,n=0,i=Math.PI*2){super(),this.type="LatheGeometry",this.parameters={points:e,segments:t,phiStart:n,phiLength:i},t=Math.floor(t),i=Tt(i,0,Math.PI*2);const r=[],o=[],a=[],l=[],c=[],h=1/t,u=new w,d=new Q,f=new w,g=new w,x=new w;let p=0,m=0;for(let _=0;_<=e.length-1;_++)switch(_){case 0:p=e[_+1].x-e[_].x,m=e[_+1].y-e[_].y,f.x=m*1,f.y=-p,f.z=m*0,x.copy(f),f.normalize(),l.push(f.x,f.y,f.z);break;case e.length-1:l.push(x.x,x.y,x.z);break;default:p=e[_+1].x-e[_].x,m=e[_+1].y-e[_].y,f.x=m*1,f.y=-p,f.z=m*0,g.copy(f),f.x+=x.x,f.y+=x.y,f.z+=x.z,f.normalize(),l.push(f.x,f.y,f.z),x.copy(g)}for(let _=0;_<=t;_++){const v=n+_*h*i,M=Math.sin(v),S=Math.cos(v);for(let E=0;E<=e.length-1;E++){u.x=e[E].x*M,u.y=e[E].y,u.z=e[E].x*S,o.push(u.x,u.y,u.z),d.x=_/t,d.y=E/(e.length-1),a.push(d.x,d.y);const C=l[3*E+0]*M,z=l[3*E+1],T=l[3*E+0]*S;c.push(C,z,T)}}for(let _=0;_<t;_++)for(let v=0;v<e.length-1;v++){const M=v+_*e.length,S=M,E=M+e.length,C=M+e.length+1,z=M+1;r.push(S,E,z),r.push(C,z,E)}this.setIndex(r),this.setAttribute("position",new Ae(o,3)),this.setAttribute("uv",new Ae(a,2)),this.setAttribute("normal",new Ae(c,3))}copy(e){return super.copy(e),this.parameters=Object.assign({},e.parameters),this}static fromJSON(e){return new jr(e.points,e.segments,e.phiStart,e.phiLength)}}class rs extends je{constructor(e=1,t=32,n=0,i=Math.PI*2){super(),this.type="CircleGeometry",this.parameters={radius:e,segments:t,thetaStart:n,thetaLength:i},t=Math.max(3,t);const r=[],o=[],a=[],l=[],c=new w,h=new Q;o.push(0,0,0),a.push(0,0,1),l.push(.5,.5);for(let u=0,d=3;u<=t;u++,d+=3){const f=n+u/t*i;c.x=e*Math.cos(f),c.y=e*Math.sin(f),o.push(c.x,c.y,c.z),a.push(0,0,1),h.x=(o[d]/e+1)/2,h.y=(o[d+1]/e+1)/2,l.push(h.x,h.y)}for(let u=1;u<=t;u++)r.push(u,u+1,0);this.setIndex(r),this.setAttribute("position",new Ae(o,3)),this.setAttribute("normal",new Ae(a,3)),this.setAttribute("uv",new Ae(l,2))}copy(e){return super.copy(e),this.parameters=Object.assign({},e.parameters),this}static fromJSON(e){return new rs(e.radius,e.segments,e.thetaStart,e.thetaLength)}}class et extends je{constructor(e=1,t=1,n=1,i=32,r=1,o=!1,a=0,l=Math.PI*2){super(),this.type="CylinderGeometry",this.parameters={radiusTop:e,radiusBottom:t,height:n,radialSegments:i,heightSegments:r,openEnded:o,thetaStart:a,thetaLength:l};const c=this;i=Math.floor(i),r=Math.floor(r);const h=[],u=[],d=[],f=[];let g=0;const x=[],p=n/2;let m=0;_(),o===!1&&(e>0&&v(!0),t>0&&v(!1)),this.setIndex(h),this.setAttribute("position",new Ae(u,3)),this.setAttribute("normal",new Ae(d,3)),this.setAttribute("uv",new Ae(f,2));function _(){const M=new w,S=new w;let E=0;const C=(t-e)/n;for(let z=0;z<=r;z++){const T=[],y=z/r,b=y*(t-e)+e;for(let D=0;D<=i;D++){const L=D/i,N=L*l+a,B=Math.sin(N),k=Math.cos(N);S.x=b*B,S.y=-y*n+p,S.z=b*k,u.push(S.x,S.y,S.z),M.set(B,C,k).normalize(),d.push(M.x,M.y,M.z),f.push(L,1-y),T.push(g++)}x.push(T)}for(let z=0;z<i;z++)for(let T=0;T<r;T++){const y=x[T][z],b=x[T+1][z],D=x[T+1][z+1],L=x[T][z+1];e>0&&(h.push(y,b,L),E+=3),t>0&&(h.push(b,D,L),E+=3)}c.addGroup(m,E,0),m+=E}function v(M){const S=g,E=new Q,C=new w;let z=0;const T=M===!0?e:t,y=M===!0?1:-1;for(let D=1;D<=i;D++)u.push(0,p*y,0),d.push(0,y,0),f.push(.5,.5),g++;const b=g;for(let D=0;D<=i;D++){const N=D/i*l+a,B=Math.cos(N),k=Math.sin(N);C.x=T*k,C.y=p*y,C.z=T*B,u.push(C.x,C.y,C.z),d.push(0,y,0),E.x=B*.5+.5,E.y=k*.5*y+.5,f.push(E.x,E.y),g++}for(let D=0;D<i;D++){const L=S+D,N=b+D;M===!0?h.push(N,N+1,L):h.push(N+1,N,L),z+=3}c.addGroup(m,z,M===!0?1:2),m+=z}}copy(e){return super.copy(e),this.parameters=Object.assign({},e.parameters),this}static fromJSON(e){return new et(e.radiusTop,e.radiusBottom,e.height,e.radialSegments,e.heightSegments,e.openEnded,e.thetaStart,e.thetaLength)}}class Kr extends et{constructor(e=1,t=1,n=32,i=1,r=!1,o=0,a=Math.PI*2){super(0,e,t,n,i,r,o,a),this.type="ConeGeometry",this.parameters={radius:e,height:t,radialSegments:n,heightSegments:i,openEnded:r,thetaStart:o,thetaLength:a}}static fromJSON(e){return new Kr(e.radius,e.height,e.radialSegments,e.heightSegments,e.openEnded,e.thetaStart,e.thetaLength)}}class Zr extends je{constructor(e=[],t=[],n=1,i=0){super(),this.type="PolyhedronGeometry",this.parameters={vertices:e,indices:t,radius:n,detail:i};const r=[],o=[];a(i),c(n),h(),this.setAttribute("position",new Ae(r,3)),this.setAttribute("normal",new Ae(r.slice(),3)),this.setAttribute("uv",new Ae(o,2)),i===0?this.computeVertexNormals():this.normalizeNormals();function a(_){const v=new w,M=new w,S=new w;for(let E=0;E<t.length;E+=3)f(t[E+0],v),f(t[E+1],M),f(t[E+2],S),l(v,M,S,_)}function l(_,v,M,S){const E=S+1,C=[];for(let z=0;z<=E;z++){C[z]=[];const T=_.clone().lerp(M,z/E),y=v.clone().lerp(M,z/E),b=E-z;for(let D=0;D<=b;D++)D===0&&z===E?C[z][D]=T:C[z][D]=T.clone().lerp(y,D/b)}for(let z=0;z<E;z++)for(let T=0;T<2*(E-z)-1;T++){const y=Math.floor(T/2);T%2===0?(d(C[z][y+1]),d(C[z+1][y]),d(C[z][y])):(d(C[z][y+1]),d(C[z+1][y+1]),d(C[z+1][y]))}}function c(_){const v=new w;for(let M=0;M<r.length;M+=3)v.x=r[M+0],v.y=r[M+1],v.z=r[M+2],v.normalize().multiplyScalar(_),r[M+0]=v.x,r[M+1]=v.y,r[M+2]=v.z}function h(){const _=new w;for(let v=0;v<r.length;v+=3){_.x=r[v+0],_.y=r[v+1],_.z=r[v+2];const M=p(_)/2/Math.PI+.5,S=m(_)/Math.PI+.5;o.push(M,1-S)}g(),u()}function u(){for(let _=0;_<o.length;_+=6){const v=o[_+0],M=o[_+2],S=o[_+4],E=Math.max(v,M,S),C=Math.min(v,M,S);E>.9&&C<.1&&(v<.2&&(o[_+0]+=1),M<.2&&(o[_+2]+=1),S<.2&&(o[_+4]+=1))}}function d(_){r.push(_.x,_.y,_.z)}function f(_,v){const M=_*3;v.x=e[M+0],v.y=e[M+1],v.z=e[M+2]}function g(){const _=new w,v=new w,M=new w,S=new w,E=new Q,C=new Q,z=new Q;for(let T=0,y=0;T<r.length;T+=9,y+=6){_.set(r[T+0],r[T+1],r[T+2]),v.set(r[T+3],r[T+4],r[T+5]),M.set(r[T+6],r[T+7],r[T+8]),E.set(o[y+0],o[y+1]),C.set(o[y+2],o[y+3]),z.set(o[y+4],o[y+5]),S.copy(_).add(v).add(M).divideScalar(3);const b=p(S);x(E,y+0,_,b),x(C,y+2,v,b),x(z,y+4,M,b)}}function x(_,v,M,S){S<0&&_.x===1&&(o[v]=_.x-1),M.x===0&&M.z===0&&(o[v]=S/2/Math.PI+.5)}function p(_){return Math.atan2(_.z,-_.x)}function m(_){return Math.atan2(-_.y,Math.sqrt(_.x*_.x+_.z*_.z))}}copy(e){return super.copy(e),this.parameters=Object.assign({},e.parameters),this}static fromJSON(e){return new Zr(e.vertices,e.indices,e.radius,e.details)}}class De extends vi{constructor(e){super(e),this.uuid=yi(),this.type="Shape",this.holes=[]}getPointsHoles(e){const t=[];for(let n=0,i=this.holes.length;n<i;n++)t[n]=this.holes[n].getPoints(e);return t}extractPoints(e){return{shape:this.getPoints(e),holes:this.getPointsHoles(e)}}copy(e){super.copy(e),this.holes=[];for(let t=0,n=e.holes.length;t<n;t++){const i=e.holes[t];this.holes.push(i.clone())}return this}toJSON(){const e=super.toJSON();e.uuid=this.uuid,e.holes=[];for(let t=0,n=this.holes.length;t<n;t++){const i=this.holes[t];e.holes.push(i.toJSON())}return e}fromJSON(e){super.fromJSON(e),this.uuid=e.uuid,this.holes=[];for(let t=0,n=e.holes.length;t<n;t++){const i=e.holes[t];this.holes.push(new vi().fromJSON(i))}return this}}const e1={triangulate:function(s,e,t=2){const n=e&&e.length,i=n?e[0]*t:s.length;let r=Kh(s,0,i,t,!0);const o=[];if(!r||r.next===r.prev)return o;let a,l,c,h,u,d,f;if(n&&(r=r1(s,e,r,t)),s.length>80*t){a=c=s[0],l=h=s[1];for(let g=t;g<i;g+=t)u=s[g],d=s[g+1],u<a&&(a=u),d<l&&(l=d),u>c&&(c=u),d>h&&(h=d);f=Math.max(c-a,h-l),f=f!==0?32767/f:0}return Ls(r,o,t,a,l,f,0),o}};function Kh(s,e,t,n,i){let r,o;if(i===g1(s,e,t,n)>0)for(r=e;r<t;r+=n)o=Ac(r,s[r],s[r+1],o);else for(r=t-n;r>=e;r-=n)o=Ac(r,s[r],s[r+1],o);return o&&Jr(o,o.next)&&(Us(o),o=o.next),o}function xi(s,e){if(!s)return s;e||(e=s);let t=s,n;do if(n=!1,!t.steiner&&(Jr(t,t.next)||yt(t.prev,t,t.next)===0)){if(Us(t),t=e=t.prev,t===t.next)break;n=!0}else t=t.next;while(n||t!==e);return e}function Ls(s,e,t,n,i,r,o){if(!s)return;!o&&r&&h1(s,n,i,r);let a=s,l,c;for(;s.prev!==s.next;){if(l=s.prev,c=s.next,r?n1(s,n,i,r):t1(s)){e.push(l.i/t|0),e.push(s.i/t|0),e.push(c.i/t|0),Us(s),s=c.next,a=c.next;continue}if(s=c,s===a){o?o===1?(s=i1(xi(s),e,t),Ls(s,e,t,n,i,r,2)):o===2&&s1(s,e,t,n,i,r):Ls(xi(s),e,t,n,i,r,1);break}}}function t1(s){const e=s.prev,t=s,n=s.next;if(yt(e,t,n)>=0)return!1;const i=e.x,r=t.x,o=n.x,a=e.y,l=t.y,c=n.y,h=i<r?i<o?i:o:r<o?r:o,u=a<l?a<c?a:c:l<c?l:c,d=i>r?i>o?i:o:r>o?r:o,f=a>l?a>c?a:c:l>c?l:c;let g=n.next;for(;g!==e;){if(g.x>=h&&g.x<=d&&g.y>=u&&g.y<=f&&Yi(i,a,r,l,o,c,g.x,g.y)&&yt(g.prev,g,g.next)>=0)return!1;g=g.next}return!0}function n1(s,e,t,n){const i=s.prev,r=s,o=s.next;if(yt(i,r,o)>=0)return!1;const a=i.x,l=r.x,c=o.x,h=i.y,u=r.y,d=o.y,f=a<l?a<c?a:c:l<c?l:c,g=h<u?h<d?h:d:u<d?u:d,x=a>l?a>c?a:c:l>c?l:c,p=h>u?h>d?h:d:u>d?u:d,m=La(f,g,e,t,n),_=La(x,p,e,t,n);let v=s.prevZ,M=s.nextZ;for(;v&&v.z>=m&&M&&M.z<=_;){if(v.x>=f&&v.x<=x&&v.y>=g&&v.y<=p&&v!==i&&v!==o&&Yi(a,h,l,u,c,d,v.x,v.y)&&yt(v.prev,v,v.next)>=0||(v=v.prevZ,M.x>=f&&M.x<=x&&M.y>=g&&M.y<=p&&M!==i&&M!==o&&Yi(a,h,l,u,c,d,M.x,M.y)&&yt(M.prev,M,M.next)>=0))return!1;M=M.nextZ}for(;v&&v.z>=m;){if(v.x>=f&&v.x<=x&&v.y>=g&&v.y<=p&&v!==i&&v!==o&&Yi(a,h,l,u,c,d,v.x,v.y)&&yt(v.prev,v,v.next)>=0)return!1;v=v.prevZ}for(;M&&M.z<=_;){if(M.x>=f&&M.x<=x&&M.y>=g&&M.y<=p&&M!==i&&M!==o&&Yi(a,h,l,u,c,d,M.x,M.y)&&yt(M.prev,M,M.next)>=0)return!1;M=M.nextZ}return!0}function i1(s,e,t){let n=s;do{const i=n.prev,r=n.next.next;!Jr(i,r)&&Zh(i,n,n.next,r)&&Ns(i,r)&&Ns(r,i)&&(e.push(i.i/t|0),e.push(n.i/t|0),e.push(r.i/t|0),Us(n),Us(n.next),n=s=r),n=n.next}while(n!==s);return xi(n)}function s1(s,e,t,n,i,r){let o=s;do{let a=o.next.next;for(;a!==o.prev;){if(o.i!==a.i&&f1(o,a)){let l=Jh(o,a);o=xi(o,o.next),l=xi(l,l.next),Ls(o,e,t,n,i,r,0),Ls(l,e,t,n,i,r,0);return}a=a.next}o=o.next}while(o!==s)}function r1(s,e,t,n){const i=[];let r,o,a,l,c;for(r=0,o=e.length;r<o;r++)a=e[r]*n,l=r<o-1?e[r+1]*n:s.length,c=Kh(s,a,l,n,!1),c===c.next&&(c.steiner=!0),i.push(d1(c));for(i.sort(o1),r=0;r<i.length;r++)t=a1(i[r],t);return t}function o1(s,e){return s.x-e.x}function a1(s,e){const t=l1(s,e);if(!t)return e;const n=Jh(t,s);return xi(n,n.next),xi(t,t.next)}function l1(s,e){let t=e,n=-1/0,i;const r=s.x,o=s.y;do{if(o<=t.y&&o>=t.next.y&&t.next.y!==t.y){const d=t.x+(o-t.y)*(t.next.x-t.x)/(t.next.y-t.y);if(d<=r&&d>n&&(n=d,i=t.x<t.next.x?t:t.next,d===r))return i}t=t.next}while(t!==e);if(!i)return null;const a=i,l=i.x,c=i.y;let h=1/0,u;t=i;do r>=t.x&&t.x>=l&&r!==t.x&&Yi(o<c?r:n,o,l,c,o<c?n:r,o,t.x,t.y)&&(u=Math.abs(o-t.y)/(r-t.x),Ns(t,s)&&(u<h||u===h&&(t.x>i.x||t.x===i.x&&c1(i,t)))&&(i=t,h=u)),t=t.next;while(t!==a);return i}function c1(s,e){return yt(s.prev,s,e.prev)<0&&yt(e.next,s,s.next)<0}function h1(s,e,t,n){let i=s;do i.z===0&&(i.z=La(i.x,i.y,e,t,n)),i.prevZ=i.prev,i.nextZ=i.next,i=i.next;while(i!==s);i.prevZ.nextZ=null,i.prevZ=null,u1(i)}function u1(s){let e,t,n,i,r,o,a,l,c=1;do{for(t=s,s=null,r=null,o=0;t;){for(o++,n=t,a=0,e=0;e<c&&(a++,n=n.nextZ,!!n);e++);for(l=c;a>0||l>0&&n;)a!==0&&(l===0||!n||t.z<=n.z)?(i=t,t=t.nextZ,a--):(i=n,n=n.nextZ,l--),r?r.nextZ=i:s=i,i.prevZ=r,r=i;t=n}r.nextZ=null,c*=2}while(o>1);return s}function La(s,e,t,n,i){return s=(s-t)*i|0,e=(e-n)*i|0,s=(s|s<<8)&16711935,s=(s|s<<4)&252645135,s=(s|s<<2)&858993459,s=(s|s<<1)&1431655765,e=(e|e<<8)&16711935,e=(e|e<<4)&252645135,e=(e|e<<2)&858993459,e=(e|e<<1)&1431655765,s|e<<1}function d1(s){let e=s,t=s;do(e.x<t.x||e.x===t.x&&e.y<t.y)&&(t=e),e=e.next;while(e!==s);return t}function Yi(s,e,t,n,i,r,o,a){return(i-o)*(e-a)>=(s-o)*(r-a)&&(s-o)*(n-a)>=(t-o)*(e-a)&&(t-o)*(r-a)>=(i-o)*(n-a)}function f1(s,e){return s.next.i!==e.i&&s.prev.i!==e.i&&!p1(s,e)&&(Ns(s,e)&&Ns(e,s)&&m1(s,e)&&(yt(s.prev,s,e.prev)||yt(s,e.prev,e))||Jr(s,e)&&yt(s.prev,s,s.next)>0&&yt(e.prev,e,e.next)>0)}function yt(s,e,t){return(e.y-s.y)*(t.x-e.x)-(e.x-s.x)*(t.y-e.y)}function Jr(s,e){return s.x===e.x&&s.y===e.y}function Zh(s,e,t,n){const i=vr(yt(s,e,t)),r=vr(yt(s,e,n)),o=vr(yt(t,n,s)),a=vr(yt(t,n,e));return!!(i!==r&&o!==a||i===0&&gr(s,t,e)||r===0&&gr(s,n,e)||o===0&&gr(t,s,n)||a===0&&gr(t,e,n))}function gr(s,e,t){return e.x<=Math.max(s.x,t.x)&&e.x>=Math.min(s.x,t.x)&&e.y<=Math.max(s.y,t.y)&&e.y>=Math.min(s.y,t.y)}function vr(s){return s>0?1:s<0?-1:0}function p1(s,e){let t=s;do{if(t.i!==s.i&&t.next.i!==s.i&&t.i!==e.i&&t.next.i!==e.i&&Zh(t,t.next,s,e))return!0;t=t.next}while(t!==s);return!1}function Ns(s,e){return yt(s.prev,s,s.next)<0?yt(s,e,s.next)>=0&&yt(s,s.prev,e)>=0:yt(s,e,s.prev)<0||yt(s,s.next,e)<0}function m1(s,e){let t=s,n=!1;const i=(s.x+e.x)/2,r=(s.y+e.y)/2;do t.y>r!=t.next.y>r&&t.next.y!==t.y&&i<(t.next.x-t.x)*(r-t.y)/(t.next.y-t.y)+t.x&&(n=!n),t=t.next;while(t!==s);return n}function Jh(s,e){const t=new Na(s.i,s.x,s.y),n=new Na(e.i,e.x,e.y),i=s.next,r=e.prev;return s.next=e,e.prev=s,t.next=i,i.prev=t,n.next=t,t.prev=n,r.next=n,n.prev=r,n}function Ac(s,e,t,n){const i=new Na(s,e,t);return n?(i.next=n.next,i.prev=n,n.next.prev=i,n.next=i):(i.prev=i,i.next=i),i}function Us(s){s.next.prev=s.prev,s.prev.next=s.next,s.prevZ&&(s.prevZ.nextZ=s.nextZ),s.nextZ&&(s.nextZ.prevZ=s.prevZ)}function Na(s,e,t){this.i=s,this.x=e,this.y=t,this.prev=null,this.next=null,this.z=0,this.prevZ=null,this.nextZ=null,this.steiner=!1}function g1(s,e,t,n){let i=0;for(let r=e,o=t-n;r<t;r+=n)i+=(s[o]-s[r])*(s[r+1]+s[o+1]),o=r;return i}class ti{static area(e){const t=e.length;let n=0;for(let i=t-1,r=0;r<t;i=r++)n+=e[i].x*e[r].y-e[r].x*e[i].y;return n*.5}static isClockWise(e){return ti.area(e)<0}static triangulateShape(e,t){const n=[],i=[],r=[];Cc(e),Pc(n,e);let o=e.length;t.forEach(Cc);for(let l=0;l<t.length;l++)i.push(o),o+=t[l].length,Pc(n,t[l]);const a=e1.triangulate(n,i);for(let l=0;l<a.length;l+=3)r.push(a.slice(l,l+3));return r}}function Cc(s){const e=s.length;e>2&&s[e-1].equals(s[0])&&s.pop()}function Pc(s,e){for(let t=0;t<e.length;t++)s.push(e[t].x),s.push(e[t].y)}class xt extends je{constructor(e=new De([new Q(.5,.5),new Q(-.5,.5),new Q(-.5,-.5),new Q(.5,-.5)]),t={}){super(),this.type="ExtrudeGeometry",this.parameters={shapes:e,options:t},e=Array.isArray(e)?e:[e];const n=this,i=[],r=[];for(let a=0,l=e.length;a<l;a++){const c=e[a];o(c)}this.setAttribute("position",new Ae(i,3)),this.setAttribute("uv",new Ae(r,2)),this.computeVertexNormals();function o(a){const l=[],c=t.curveSegments!==void 0?t.curveSegments:12,h=t.steps!==void 0?t.steps:1,u=t.depth!==void 0?t.depth:1;let d=t.bevelEnabled!==void 0?t.bevelEnabled:!0,f=t.bevelThickness!==void 0?t.bevelThickness:.2,g=t.bevelSize!==void 0?t.bevelSize:f-.1,x=t.bevelOffset!==void 0?t.bevelOffset:0,p=t.bevelSegments!==void 0?t.bevelSegments:3;const m=t.extrudePath,_=t.UVGenerator!==void 0?t.UVGenerator:v1;let v,M=!1,S,E,C,z;m&&(v=m.getSpacedPoints(h),M=!0,d=!1,S=m.computeFrenetFrames(h,!1),E=new w,C=new w,z=new w),d||(p=0,f=0,g=0,x=0);const T=a.extractPoints(c);let y=T.shape;const b=T.holes;if(!ti.isClockWise(y)){y=y.reverse();for(let te=0,I=b.length;te<I;te++){const ce=b[te];ti.isClockWise(ce)&&(b[te]=ce.reverse())}}const L=ti.triangulateShape(y,b),N=y;for(let te=0,I=b.length;te<I;te++){const ce=b[te];y=y.concat(ce)}function B(te,I,ce){return I||console.error("THREE.ExtrudeGeometry: vec does not exist"),te.clone().addScaledVector(I,ce)}const k=y.length,q=L.length;function U(te,I,ce){let ae,se,de;const xe=te.x-I.x,pe=te.y-I.y,F=ce.x-te.x,A=ce.y-te.y,j=xe*xe+pe*pe,ne=xe*A-pe*F;if(Math.abs(ne)>Number.EPSILON){const re=Math.sqrt(j),ie=Math.sqrt(F*F+A*A),Pe=I.x-pe/re,me=I.y+xe/re,we=ce.x-A/ie,Ze=ce.y+F/ie,ue=((we-Pe)*A-(Ze-me)*F)/(xe*A-pe*F);ae=Pe+xe*ue-te.x,se=me+pe*ue-te.y;const Se=ae*ae+se*se;if(Se<=2)return new Q(ae,se);de=Math.sqrt(Se/2)}else{let re=!1;xe>Number.EPSILON?F>Number.EPSILON&&(re=!0):xe<-Number.EPSILON?F<-Number.EPSILON&&(re=!0):Math.sign(pe)===Math.sign(A)&&(re=!0),re?(ae=-pe,se=xe,de=Math.sqrt(j)):(ae=xe,se=pe,de=Math.sqrt(j/2))}return new Q(ae/de,se/de)}const V=[];for(let te=0,I=N.length,ce=I-1,ae=te+1;te<I;te++,ce++,ae++)ce===I&&(ce=0),ae===I&&(ae=0),V[te]=U(N[te],N[ce],N[ae]);const P=[];let O,H=V.concat();for(let te=0,I=b.length;te<I;te++){const ce=b[te];O=[];for(let ae=0,se=ce.length,de=se-1,xe=ae+1;ae<se;ae++,de++,xe++)de===se&&(de=0),xe===se&&(xe=0),O[ae]=U(ce[ae],ce[de],ce[xe]);P.push(O),H=H.concat(O)}for(let te=0;te<p;te++){const I=te/p,ce=f*Math.cos(I*Math.PI/2),ae=g*Math.sin(I*Math.PI/2)+x;for(let se=0,de=N.length;se<de;se++){const xe=B(N[se],V[se],ae);he(xe.x,xe.y,-ce)}for(let se=0,de=b.length;se<de;se++){const xe=b[se];O=P[se];for(let pe=0,F=xe.length;pe<F;pe++){const A=B(xe[pe],O[pe],ae);he(A.x,A.y,-ce)}}}const Z=g+x;for(let te=0;te<k;te++){const I=d?B(y[te],H[te],Z):y[te];M?(C.copy(S.normals[0]).multiplyScalar(I.x),E.copy(S.binormals[0]).multiplyScalar(I.y),z.copy(v[0]).add(C).add(E),he(z.x,z.y,z.z)):he(I.x,I.y,0)}for(let te=1;te<=h;te++)for(let I=0;I<k;I++){const ce=d?B(y[I],H[I],Z):y[I];M?(C.copy(S.normals[te]).multiplyScalar(ce.x),E.copy(S.binormals[te]).multiplyScalar(ce.y),z.copy(v[te]).add(C).add(E),he(z.x,z.y,z.z)):he(ce.x,ce.y,u/h*te)}for(let te=p-1;te>=0;te--){const I=te/p,ce=f*Math.cos(I*Math.PI/2),ae=g*Math.sin(I*Math.PI/2)+x;for(let se=0,de=N.length;se<de;se++){const xe=B(N[se],V[se],ae);he(xe.x,xe.y,u+ce)}for(let se=0,de=b.length;se<de;se++){const xe=b[se];O=P[se];for(let pe=0,F=xe.length;pe<F;pe++){const A=B(xe[pe],O[pe],ae);M?he(A.x,A.y+v[h-1].y,v[h-1].x+ce):he(A.x,A.y,u+ce)}}}W(),$();function W(){const te=i.length/3;if(d){let I=0,ce=k*I;for(let ae=0;ae<q;ae++){const se=L[ae];Ce(se[2]+ce,se[1]+ce,se[0]+ce)}I=h+p*2,ce=k*I;for(let ae=0;ae<q;ae++){const se=L[ae];Ce(se[0]+ce,se[1]+ce,se[2]+ce)}}else{for(let I=0;I<q;I++){const ce=L[I];Ce(ce[2],ce[1],ce[0])}for(let I=0;I<q;I++){const ce=L[I];Ce(ce[0]+k*h,ce[1]+k*h,ce[2]+k*h)}}n.addGroup(te,i.length/3-te,0)}function $(){const te=i.length/3;let I=0;le(N,I),I+=N.length;for(let ce=0,ae=b.length;ce<ae;ce++){const se=b[ce];le(se,I),I+=se.length}n.addGroup(te,i.length/3-te,1)}function le(te,I){let ce=te.length;for(;--ce>=0;){const ae=ce;let se=ce-1;se<0&&(se=te.length-1);for(let de=0,xe=h+p*2;de<xe;de++){const pe=k*de,F=k*(de+1),A=I+ae+pe,j=I+se+pe,ne=I+se+F,re=I+ae+F;Oe(A,j,ne,re)}}}function he(te,I,ce){l.push(te),l.push(I),l.push(ce)}function Ce(te,I,ce){Ie(te),Ie(I),Ie(ce);const ae=i.length/3,se=_.generateTopUV(n,i,ae-3,ae-2,ae-1);ze(se[0]),ze(se[1]),ze(se[2])}function Oe(te,I,ce,ae){Ie(te),Ie(I),Ie(ae),Ie(I),Ie(ce),Ie(ae);const se=i.length/3,de=_.generateSideWallUV(n,i,se-6,se-3,se-2,se-1);ze(de[0]),ze(de[1]),ze(de[3]),ze(de[1]),ze(de[2]),ze(de[3])}function Ie(te){i.push(l[te*3+0]),i.push(l[te*3+1]),i.push(l[te*3+2])}function ze(te){r.push(te.x),r.push(te.y)}}}copy(e){return super.copy(e),this.parameters=Object.assign({},e.parameters),this}toJSON(){const e=super.toJSON(),t=this.parameters.shapes,n=this.parameters.options;return x1(t,n,e)}static fromJSON(e,t){const n=[];for(let r=0,o=e.shapes.length;r<o;r++){const a=t[e.shapes[r]];n.push(a)}const i=e.options.extrudePath;return i!==void 0&&(e.options.extrudePath=new kr[i.type]().fromJSON(i)),new xt(n,e.options)}}const v1={generateTopUV:function(s,e,t,n,i){const r=e[t*3],o=e[t*3+1],a=e[n*3],l=e[n*3+1],c=e[i*3],h=e[i*3+1];return[new Q(r,o),new Q(a,l),new Q(c,h)]},generateSideWallUV:function(s,e,t,n,i,r){const o=e[t*3],a=e[t*3+1],l=e[t*3+2],c=e[n*3],h=e[n*3+1],u=e[n*3+2],d=e[i*3],f=e[i*3+1],g=e[i*3+2],x=e[r*3],p=e[r*3+1],m=e[r*3+2];return Math.abs(a-h)<Math.abs(o-c)?[new Q(o,1-l),new Q(c,1-u),new Q(d,1-g),new Q(x,1-m)]:[new Q(a,1-l),new Q(h,1-u),new Q(f,1-g),new Q(p,1-m)]}};function x1(s,e,t){if(t.shapes=[],Array.isArray(s))for(let n=0,i=s.length;n<i;n++){const r=s[n];t.shapes.push(r.uuid)}else t.shapes.push(s.uuid);return t.options=Object.assign({},e),e.extrudePath!==void 0&&(t.options.extrudePath=e.extrudePath.toJSON()),t}class zs extends Zr{constructor(e=1,t=0){const n=(1+Math.sqrt(5))/2,i=[-1,n,0,1,n,0,-1,-n,0,1,-n,0,0,-1,n,0,1,n,0,-1,-n,0,1,-n,n,0,-1,n,0,1,-n,0,-1,-n,0,1],r=[0,11,5,0,5,1,0,1,7,0,7,10,0,10,11,1,5,9,5,11,4,11,10,2,10,7,6,7,1,8,3,9,4,3,4,2,3,2,6,3,6,8,3,8,9,4,9,5,2,4,11,6,2,10,8,6,7,9,8,1];super(i,r,e,t),this.type="IcosahedronGeometry",this.parameters={radius:e,detail:t}}static fromJSON(e){return new zs(e.radius,e.detail)}}class qt extends Zr{constructor(e=1,t=0){const n=[1,0,0,-1,0,0,0,1,0,0,-1,0,0,0,1,0,0,-1],i=[0,2,4,0,4,3,0,3,5,0,5,2,1,2,5,1,5,3,1,3,4,1,4,2];super(n,i,e,t),this.type="OctahedronGeometry",this.parameters={radius:e,detail:t}}static fromJSON(e){return new qt(e.radius,e.detail)}}class $r extends je{constructor(e=new De([new Q(0,.5),new Q(-.5,-.5),new Q(.5,-.5)]),t=12){super(),this.type="ShapeGeometry",this.parameters={shapes:e,curveSegments:t};const n=[],i=[],r=[],o=[];let a=0,l=0;if(Array.isArray(e)===!1)c(e);else for(let h=0;h<e.length;h++)c(e[h]),this.addGroup(a,l,h),a+=l,l=0;this.setIndex(n),this.setAttribute("position",new Ae(i,3)),this.setAttribute("normal",new Ae(r,3)),this.setAttribute("uv",new Ae(o,2));function c(h){const u=i.length/3,d=h.extractPoints(t);let f=d.shape;const g=d.holes;ti.isClockWise(f)===!1&&(f=f.reverse());for(let p=0,m=g.length;p<m;p++){const _=g[p];ti.isClockWise(_)===!0&&(g[p]=_.reverse())}const x=ti.triangulateShape(f,g);for(let p=0,m=g.length;p<m;p++){const _=g[p];f=f.concat(_)}for(let p=0,m=f.length;p<m;p++){const _=f[p];i.push(_.x,_.y,0),r.push(0,0,1),o.push(_.x,_.y)}for(let p=0,m=x.length;p<m;p++){const _=x[p],v=_[0]+u,M=_[1]+u,S=_[2]+u;n.push(v,M,S),l+=3}}}copy(e){return super.copy(e),this.parameters=Object.assign({},e.parameters),this}toJSON(){const e=super.toJSON(),t=this.parameters.shapes;return _1(t,e)}static fromJSON(e,t){const n=[];for(let i=0,r=e.shapes.length;i<r;i++){const o=t[e.shapes[i]];n.push(o)}return new $r(n,e.curveSegments)}}function _1(s,e){if(e.shapes=[],Array.isArray(s))for(let t=0,n=s.length;t<n;t++){const i=s[t];e.shapes.push(i.uuid)}else e.shapes.push(s.uuid);return e}class ft extends je{constructor(e=1,t=32,n=16,i=0,r=Math.PI*2,o=0,a=Math.PI){super(),this.type="SphereGeometry",this.parameters={radius:e,widthSegments:t,heightSegments:n,phiStart:i,phiLength:r,thetaStart:o,thetaLength:a},t=Math.max(3,Math.floor(t)),n=Math.max(2,Math.floor(n));const l=Math.min(o+a,Math.PI);let c=0;const h=[],u=new w,d=new w,f=[],g=[],x=[],p=[];for(let m=0;m<=n;m++){const _=[],v=m/n;let M=0;m===0&&o===0?M=.5/t:m===n&&l===Math.PI&&(M=-.5/t);for(let S=0;S<=t;S++){const E=S/t;u.x=-e*Math.cos(i+E*r)*Math.sin(o+v*a),u.y=e*Math.cos(o+v*a),u.z=e*Math.sin(i+E*r)*Math.sin(o+v*a),g.push(u.x,u.y,u.z),d.copy(u).normalize(),x.push(d.x,d.y,d.z),p.push(E+M,1-v),_.push(c++)}h.push(_)}for(let m=0;m<n;m++)for(let _=0;_<t;_++){const v=h[m][_+1],M=h[m][_],S=h[m+1][_],E=h[m+1][_+1];(m!==0||o>0)&&f.push(v,M,E),(m!==n-1||l<Math.PI)&&f.push(M,S,E)}this.setIndex(f),this.setAttribute("position",new Ae(g,3)),this.setAttribute("normal",new Ae(x,3)),this.setAttribute("uv",new Ae(p,2))}copy(e){return super.copy(e),this.parameters=Object.assign({},e.parameters),this}static fromJSON(e){return new ft(e.radius,e.widthSegments,e.heightSegments,e.phiStart,e.phiLength,e.thetaStart,e.thetaLength)}}class at extends je{constructor(e=1,t=.4,n=12,i=48,r=Math.PI*2){super(),this.type="TorusGeometry",this.parameters={radius:e,tube:t,radialSegments:n,tubularSegments:i,arc:r},n=Math.floor(n),i=Math.floor(i);const o=[],a=[],l=[],c=[],h=new w,u=new w,d=new w;for(let f=0;f<=n;f++)for(let g=0;g<=i;g++){const x=g/i*r,p=f/n*Math.PI*2;u.x=(e+t*Math.cos(p))*Math.cos(x),u.y=(e+t*Math.cos(p))*Math.sin(x),u.z=t*Math.sin(p),a.push(u.x,u.y,u.z),h.x=e*Math.cos(x),h.y=e*Math.sin(x),d.subVectors(u,h).normalize(),l.push(d.x,d.y,d.z),c.push(g/i),c.push(f/n)}for(let f=1;f<=n;f++)for(let g=1;g<=i;g++){const x=(i+1)*f+g-1,p=(i+1)*(f-1)+g-1,m=(i+1)*(f-1)+g,_=(i+1)*f+g;o.push(x,p,_),o.push(p,m,_)}this.setIndex(o),this.setAttribute("position",new Ae(a,3)),this.setAttribute("normal",new Ae(l,3)),this.setAttribute("uv",new Ae(c,2))}copy(e){return super.copy(e),this.parameters=Object.assign({},e.parameters),this}static fromJSON(e){return new at(e.radius,e.tube,e.radialSegments,e.tubularSegments,e.arc)}}class Si extends je{constructor(e=new qh(new w(-1,-1,0),new w(-1,1,0),new w(1,1,0)),t=64,n=1,i=8,r=!1){super(),this.type="TubeGeometry",this.parameters={path:e,tubularSegments:t,radius:n,radialSegments:i,closed:r};const o=e.computeFrenetFrames(t,r);this.tangents=o.tangents,this.normals=o.normals,this.binormals=o.binormals;const a=new w,l=new w,c=new Q;let h=new w;const u=[],d=[],f=[],g=[];x(),this.setIndex(g),this.setAttribute("position",new Ae(u,3)),this.setAttribute("normal",new Ae(d,3)),this.setAttribute("uv",new Ae(f,2));function x(){for(let v=0;v<t;v++)p(v);p(r===!1?t:0),_(),m()}function p(v){h=e.getPointAt(v/t,h);const M=o.normals[v],S=o.binormals[v];for(let E=0;E<=i;E++){const C=E/i*Math.PI*2,z=Math.sin(C),T=-Math.cos(C);l.x=T*M.x+z*S.x,l.y=T*M.y+z*S.y,l.z=T*M.z+z*S.z,l.normalize(),d.push(l.x,l.y,l.z),a.x=h.x+n*l.x,a.y=h.y+n*l.y,a.z=h.z+n*l.z,u.push(a.x,a.y,a.z)}}function m(){for(let v=1;v<=t;v++)for(let M=1;M<=i;M++){const S=(i+1)*(v-1)+(M-1),E=(i+1)*v+(M-1),C=(i+1)*v+M,z=(i+1)*(v-1)+M;g.push(S,E,z),g.push(E,C,z)}}function _(){for(let v=0;v<=t;v++)for(let M=0;M<=i;M++)c.x=v/t,c.y=M/i,f.push(c.x,c.y)}}copy(e){return super.copy(e),this.parameters=Object.assign({},e.parameters),this}toJSON(){const e=super.toJSON();return e.path=this.parameters.path.toJSON(),e}static fromJSON(e){return new Si(new kr[e.path.type]().fromJSON(e.path),e.tubularSegments,e.radius,e.radialSegments,e.closed)}}class y1 extends je{constructor(e=null){if(super(),this.type="WireframeGeometry",this.parameters={geometry:e},e!==null){const t=[],n=new Set,i=new w,r=new w;if(e.index!==null){const o=e.attributes.position,a=e.index;let l=e.groups;l.length===0&&(l=[{start:0,count:a.count,materialIndex:0}]);for(let c=0,h=l.length;c<h;++c){const u=l[c],d=u.start,f=u.count;for(let g=d,x=d+f;g<x;g+=3)for(let p=0;p<3;p++){const m=a.getX(g+p),_=a.getX(g+(p+1)%3);i.fromBufferAttribute(o,m),r.fromBufferAttribute(o,_),Rc(i,r,n)===!0&&(t.push(i.x,i.y,i.z),t.push(r.x,r.y,r.z))}}}else{const o=e.attributes.position;for(let a=0,l=o.count/3;a<l;a++)for(let c=0;c<3;c++){const h=3*a+c,u=3*a+(c+1)%3;i.fromBufferAttribute(o,h),r.fromBufferAttribute(o,u),Rc(i,r,n)===!0&&(t.push(i.x,i.y,i.z),t.push(r.x,r.y,r.z))}}this.setAttribute("position",new Ae(t,3))}}copy(e){return super.copy(e),this.parameters=Object.assign({},e.parameters),this}}function Rc(s,e,t){const n=`${s.x},${s.y},${s.z}-${e.x},${e.y},${e.z}`,i=`${e.x},${e.y},${e.z}-${s.x},${s.y},${s.z}`;return t.has(n)===!0||t.has(i)===!0?!1:(t.add(n),t.add(i),!0)}class M1 extends gt{constructor(e){super(e),this.isRawShaderMaterial=!0,this.type="RawShaderMaterial"}}class Ke extends wi{constructor(e){super(),this.isMeshStandardMaterial=!0,this.defines={STANDARD:""},this.type="MeshStandardMaterial",this.color=new Ne(16777215),this.roughness=1,this.metalness=0,this.map=null,this.lightMap=null,this.lightMapIntensity=1,this.aoMap=null,this.aoMapIntensity=1,this.emissive=new Ne(0),this.emissiveIntensity=1,this.emissiveMap=null,this.bumpMap=null,this.bumpScale=1,this.normalMap=null,this.normalMapType=Eh,this.normalScale=new Q(1,1),this.displacementMap=null,this.displacementScale=1,this.displacementBias=0,this.roughnessMap=null,this.metalnessMap=null,this.alphaMap=null,this.envMap=null,this.envMapRotation=new Yt,this.envMapIntensity=1,this.wireframe=!1,this.wireframeLinewidth=1,this.wireframeLinecap="round",this.wireframeLinejoin="round",this.flatShading=!1,this.fog=!0,this.setValues(e)}copy(e){return super.copy(e),this.defines={STANDARD:""},this.color.copy(e.color),this.roughness=e.roughness,this.metalness=e.metalness,this.map=e.map,this.lightMap=e.lightMap,this.lightMapIntensity=e.lightMapIntensity,this.aoMap=e.aoMap,this.aoMapIntensity=e.aoMapIntensity,this.emissive.copy(e.emissive),this.emissiveMap=e.emissiveMap,this.emissiveIntensity=e.emissiveIntensity,this.bumpMap=e.bumpMap,this.bumpScale=e.bumpScale,this.normalMap=e.normalMap,this.normalMapType=e.normalMapType,this.normalScale.copy(e.normalScale),this.displacementMap=e.displacementMap,this.displacementScale=e.displacementScale,this.displacementBias=e.displacementBias,this.roughnessMap=e.roughnessMap,this.metalnessMap=e.metalnessMap,this.alphaMap=e.alphaMap,this.envMap=e.envMap,this.envMapRotation.copy(e.envMapRotation),this.envMapIntensity=e.envMapIntensity,this.wireframe=e.wireframe,this.wireframeLinewidth=e.wireframeLinewidth,this.wireframeLinecap=e.wireframeLinecap,this.wireframeLinejoin=e.wireframeLinejoin,this.flatShading=e.flatShading,this.fog=e.fog,this}}class $h extends Ke{constructor(e){super(),this.isMeshPhysicalMaterial=!0,this.defines={STANDARD:"",PHYSICAL:""},this.type="MeshPhysicalMaterial",this.anisotropyRotation=0,this.anisotropyMap=null,this.clearcoatMap=null,this.clearcoatRoughness=0,this.clearcoatRoughnessMap=null,this.clearcoatNormalScale=new Q(1,1),this.clearcoatNormalMap=null,this.ior=1.5,Object.defineProperty(this,"reflectivity",{get:function(){return Tt(2.5*(this.ior-1)/(this.ior+1),0,1)},set:function(t){this.ior=(1+.4*t)/(1-.4*t)}}),this.iridescenceMap=null,this.iridescenceIOR=1.3,this.iridescenceThicknessRange=[100,400],this.iridescenceThicknessMap=null,this.sheenColor=new Ne(0),this.sheenColorMap=null,this.sheenRoughness=1,this.sheenRoughnessMap=null,this.transmissionMap=null,this.thickness=0,this.thicknessMap=null,this.attenuationDistance=1/0,this.attenuationColor=new Ne(1,1,1),this.specularIntensity=1,this.specularIntensityMap=null,this.specularColor=new Ne(1,1,1),this.specularColorMap=null,this._anisotropy=0,this._clearcoat=0,this._dispersion=0,this._iridescence=0,this._sheen=0,this._transmission=0,this.setValues(e)}get anisotropy(){return this._anisotropy}set anisotropy(e){this._anisotropy>0!=e>0&&this.version++,this._anisotropy=e}get clearcoat(){return this._clearcoat}set clearcoat(e){this._clearcoat>0!=e>0&&this.version++,this._clearcoat=e}get iridescence(){return this._iridescence}set iridescence(e){this._iridescence>0!=e>0&&this.version++,this._iridescence=e}get dispersion(){return this._dispersion}set dispersion(e){this._dispersion>0!=e>0&&this.version++,this._dispersion=e}get sheen(){return this._sheen}set sheen(e){this._sheen>0!=e>0&&this.version++,this._sheen=e}get transmission(){return this._transmission}set transmission(e){this._transmission>0!=e>0&&this.version++,this._transmission=e}copy(e){return super.copy(e),this.defines={STANDARD:"",PHYSICAL:""},this.anisotropy=e.anisotropy,this.anisotropyRotation=e.anisotropyRotation,this.anisotropyMap=e.anisotropyMap,this.clearcoat=e.clearcoat,this.clearcoatMap=e.clearcoatMap,this.clearcoatRoughness=e.clearcoatRoughness,this.clearcoatRoughnessMap=e.clearcoatRoughnessMap,this.clearcoatNormalMap=e.clearcoatNormalMap,this.clearcoatNormalScale.copy(e.clearcoatNormalScale),this.dispersion=e.dispersion,this.ior=e.ior,this.iridescence=e.iridescence,this.iridescenceMap=e.iridescenceMap,this.iridescenceIOR=e.iridescenceIOR,this.iridescenceThicknessRange=[...e.iridescenceThicknessRange],this.iridescenceThicknessMap=e.iridescenceThicknessMap,this.sheen=e.sheen,this.sheenColor.copy(e.sheenColor),this.sheenColorMap=e.sheenColorMap,this.sheenRoughness=e.sheenRoughness,this.sheenRoughnessMap=e.sheenRoughnessMap,this.transmission=e.transmission,this.transmissionMap=e.transmissionMap,this.thickness=e.thickness,this.thicknessMap=e.thicknessMap,this.attenuationDistance=e.attenuationDistance,this.attenuationColor.copy(e.attenuationColor),this.specularIntensity=e.specularIntensity,this.specularIntensityMap=e.specularIntensityMap,this.specularColor.copy(e.specularColor),this.specularColorMap=e.specularColorMap,this}}class Qr extends Mt{constructor(e,t=1){super(),this.isLight=!0,this.type="Light",this.color=new Ne(e),this.intensity=t}dispose(){}copy(e,t){return super.copy(e,t),this.color.copy(e.color),this.intensity=e.intensity,this}toJSON(e){const t=super.toJSON(e);return t.object.color=this.color.getHex(),t.object.intensity=this.intensity,this.groundColor!==void 0&&(t.object.groundColor=this.groundColor.getHex()),this.distance!==void 0&&(t.object.distance=this.distance),this.angle!==void 0&&(t.object.angle=this.angle),this.decay!==void 0&&(t.object.decay=this.decay),this.penumbra!==void 0&&(t.object.penumbra=this.penumbra),this.shadow!==void 0&&(t.object.shadow=this.shadow.toJSON()),this.target!==void 0&&(t.object.target=this.target.uuid),t}}class Ua extends Qr{constructor(e,t,n){super(e,n),this.isHemisphereLight=!0,this.type="HemisphereLight",this.position.copy(Mt.DEFAULT_UP),this.updateMatrix(),this.groundColor=new Ne(t)}copy(e,t){return super.copy(e,t),this.groundColor.copy(e.groundColor),this}}const zo=new Fe,Dc=new w,Ic=new w;class cl{constructor(e){this.camera=e,this.intensity=1,this.bias=0,this.normalBias=0,this.radius=1,this.blurSamples=8,this.mapSize=new Q(512,512),this.map=null,this.mapPass=null,this.matrix=new Fe,this.autoUpdate=!0,this.needsUpdate=!1,this._frustum=new el,this._frameExtents=new Q(1,1),this._viewportCount=1,this._viewports=[new ot(0,0,1,1)]}getViewportCount(){return this._viewportCount}getFrustum(){return this._frustum}updateMatrices(e){const t=this.camera,n=this.matrix;Dc.setFromMatrixPosition(e.matrixWorld),t.position.copy(Dc),Ic.setFromMatrixPosition(e.target.matrixWorld),t.lookAt(Ic),t.updateMatrixWorld(),zo.multiplyMatrices(t.projectionMatrix,t.matrixWorldInverse),this._frustum.setFromProjectionMatrix(zo),n.set(.5,0,0,.5,0,.5,0,.5,0,0,.5,.5,0,0,0,1),n.multiply(zo)}getViewport(e){return this._viewports[e]}getFrameExtents(){return this._frameExtents}dispose(){this.map&&this.map.dispose(),this.mapPass&&this.mapPass.dispose()}copy(e){return this.camera=e.camera.clone(),this.intensity=e.intensity,this.bias=e.bias,this.radius=e.radius,this.mapSize.copy(e.mapSize),this}clone(){return new this.constructor().copy(this)}toJSON(){const e={};return this.intensity!==1&&(e.intensity=this.intensity),this.bias!==0&&(e.bias=this.bias),this.normalBias!==0&&(e.normalBias=this.normalBias),this.radius!==1&&(e.radius=this.radius),(this.mapSize.x!==512||this.mapSize.y!==512)&&(e.mapSize=this.mapSize.toArray()),e.camera=this.camera.toJSON(!1).object,delete e.camera.matrix,e}}class b1 extends cl{constructor(){super(new Jt(50,1,.5,500)),this.isSpotLightShadow=!0,this.focus=1}updateMatrices(e){const t=this.camera,n=ns*2*e.angle*this.focus,i=this.mapSize.width/this.mapSize.height,r=e.distance||t.far;(n!==t.fov||i!==t.aspect||r!==t.far)&&(t.fov=n,t.aspect=i,t.far=r,t.updateProjectionMatrix()),super.updateMatrices(e)}copy(e){return super.copy(e),this.focus=e.focus,this}}class w1 extends Qr{constructor(e,t,n=0,i=Math.PI/3,r=0,o=2){super(e,t),this.isSpotLight=!0,this.type="SpotLight",this.position.copy(Mt.DEFAULT_UP),this.updateMatrix(),this.target=new Mt,this.distance=n,this.angle=i,this.penumbra=r,this.decay=o,this.map=null,this.shadow=new b1}get power(){return this.intensity*Math.PI}set power(e){this.intensity=e/Math.PI}dispose(){this.shadow.dispose()}copy(e,t){return super.copy(e,t),this.distance=e.distance,this.angle=e.angle,this.penumbra=e.penumbra,this.decay=e.decay,this.target=e.target.clone(),this.shadow=e.shadow.clone(),this}}const Lc=new Fe,_s=new w,ko=new w;class S1 extends cl{constructor(){super(new Jt(90,1,.5,500)),this.isPointLightShadow=!0,this._frameExtents=new Q(4,2),this._viewportCount=6,this._viewports=[new ot(2,1,1,1),new ot(0,1,1,1),new ot(3,1,1,1),new ot(1,1,1,1),new ot(3,0,1,1),new ot(1,0,1,1)],this._cubeDirections=[new w(1,0,0),new w(-1,0,0),new w(0,0,1),new w(0,0,-1),new w(0,1,0),new w(0,-1,0)],this._cubeUps=[new w(0,1,0),new w(0,1,0),new w(0,1,0),new w(0,1,0),new w(0,0,1),new w(0,0,-1)]}updateMatrices(e,t=0){const n=this.camera,i=this.matrix,r=e.distance||n.far;r!==n.far&&(n.far=r,n.updateProjectionMatrix()),_s.setFromMatrixPosition(e.matrixWorld),n.position.copy(_s),ko.copy(n.position),ko.add(this._cubeDirections[t]),n.up.copy(this._cubeUps[t]),n.lookAt(ko),n.updateMatrixWorld(),i.makeTranslation(-_s.x,-_s.y,-_s.z),Lc.multiplyMatrices(n.projectionMatrix,n.matrixWorldInverse),this._frustum.setFromProjectionMatrix(Lc)}}class Bn extends Qr{constructor(e,t,n=0,i=2){super(e,t),this.isPointLight=!0,this.type="PointLight",this.distance=n,this.decay=i,this.shadow=new S1}get power(){return this.intensity*4*Math.PI}set power(e){this.intensity=e/(4*Math.PI)}dispose(){this.shadow.dispose()}copy(e,t){return super.copy(e,t),this.distance=e.distance,this.decay=e.decay,this.shadow=e.shadow.clone(),this}}class T1 extends cl{constructor(){super(new tl(-5,5,5,-5,.5,500)),this.isDirectionalLightShadow=!0}}class ws extends Qr{constructor(e,t){super(e,t),this.isDirectionalLight=!0,this.type="DirectionalLight",this.position.copy(Mt.DEFAULT_UP),this.updateMatrix(),this.target=new Mt,this.shadow=new T1}dispose(){this.shadow.dispose()}copy(e){return super.copy(e),this.target=e.target.clone(),this.shadow=e.shadow.clone(),this}}class E1{constructor(e=!0){this.autoStart=e,this.startTime=0,this.oldTime=0,this.elapsedTime=0,this.running=!1}start(){this.startTime=Nc(),this.oldTime=this.startTime,this.elapsedTime=0,this.running=!0}stop(){this.getElapsedTime(),this.running=!1,this.autoStart=!1}getElapsedTime(){return this.getDelta(),this.elapsedTime}getDelta(){let e=0;if(this.autoStart&&!this.running)return this.start(),0;if(this.running){const t=Nc();e=(t-this.oldTime)/1e3,this.oldTime=t,this.elapsedTime+=e}return e}}function Nc(){return performance.now()}const Uc=new Fe;class hl{constructor(e,t,n=0,i=1/0){this.ray=new bi(e,t),this.near=n,this.far=i,this.camera=null,this.layers=new Qa,this.params={Mesh:{},Line:{threshold:1},LOD:{},Points:{threshold:1},Sprite:{}}}set(e,t){this.ray.set(e,t)}setFromCamera(e,t){t.isPerspectiveCamera?(this.ray.origin.setFromMatrixPosition(t.matrixWorld),this.ray.direction.set(e.x,e.y,.5).unproject(t).sub(this.ray.origin).normalize(),this.camera=t):t.isOrthographicCamera?(this.ray.origin.set(e.x,e.y,(t.near+t.far)/(t.near-t.far)).unproject(t),this.ray.direction.set(0,0,-1).transformDirection(t.matrixWorld),this.camera=t):console.error("THREE.Raycaster: Unsupported camera type: "+t.type)}setFromXRController(e){return Uc.identity().extractRotation(e.matrixWorld),this.ray.origin.setFromMatrixPosition(e.matrixWorld),this.ray.direction.set(0,0,-1).applyMatrix4(Uc),this}intersectObject(e,t=!0,n=[]){return Oa(e,this,n,t),n.sort(Oc),n}intersectObjects(e,t=!0,n=[]){for(let i=0,r=e.length;i<r;i++)Oa(e[i],this,n,t);return n.sort(Oc),n}}function Oc(s,e){return s.distance-e.distance}function Oa(s,e,t,n){let i=!0;if(s.layers.test(e.layers)&&s.raycast(e,t)===!1&&(i=!1),i===!0&&n===!0){const r=s.children;for(let o=0,a=r.length;o<a;o++)Oa(r[o],e,t,!0)}}class Fc{constructor(e=1,t=0,n=0){return this.radius=e,this.phi=t,this.theta=n,this}set(e,t,n){return this.radius=e,this.phi=t,this.theta=n,this}copy(e){return this.radius=e.radius,this.phi=e.phi,this.theta=e.theta,this}makeSafe(){return this.phi=Math.max(1e-6,Math.min(Math.PI-1e-6,this.phi)),this}setFromVector3(e){return this.setFromCartesianCoords(e.x,e.y,e.z)}setFromCartesianCoords(e,t,n){return this.radius=Math.sqrt(e*e+t*t+n*n),this.radius===0?(this.theta=0,this.phi=0):(this.theta=Math.atan2(e,n),this.phi=Math.acos(Tt(t/this.radius,-1,1))),this}clone(){return new this.constructor().copy(this)}}class A1 extends _i{constructor(e,t=null){super(),this.object=e,this.domElement=t,this.enabled=!0,this.state=-1,this.keys={},this.mouseButtons={LEFT:null,MIDDLE:null,RIGHT:null},this.touches={ONE:null,TWO:null}}connect(){}disconnect(){}dispose(){}update(){}}typeof __THREE_DEVTOOLS__<"u"&&__THREE_DEVTOOLS__.dispatchEvent(new CustomEvent("register",{detail:{revision:Ga}}));typeof window<"u"&&(window.__THREE__?console.warn("WARNING: Multiple instances of Three.js being imported."):window.__THREE__=Ga);const zc={type:"change"},ul={type:"start"},Qh={type:"end"},xr=new bi,kc=new Jn,C1=Math.cos(70*_t.DEG2RAD),Rt=new w,Zt=2*Math.PI,ct={NONE:-1,ROTATE:0,DOLLY:1,PAN:2,TOUCH_ROTATE:3,TOUCH_PAN:4,TOUCH_DOLLY_PAN:5,TOUCH_DOLLY_ROTATE:6},Bo=1e-6;class P1 extends A1{constructor(e,t=null){super(e,t),this.state=ct.NONE,this.enabled=!0,this.target=new w,this.cursor=new w,this.minDistance=0,this.maxDistance=1/0,this.minZoom=0,this.maxZoom=1/0,this.minTargetRadius=0,this.maxTargetRadius=1/0,this.minPolarAngle=0,this.maxPolarAngle=Math.PI,this.minAzimuthAngle=-1/0,this.maxAzimuthAngle=1/0,this.enableDamping=!1,this.dampingFactor=.05,this.enableZoom=!0,this.zoomSpeed=1,this.enableRotate=!0,this.rotateSpeed=1,this.enablePan=!0,this.panSpeed=1,this.screenSpacePanning=!0,this.keyPanSpeed=7,this.zoomToCursor=!1,this.autoRotate=!1,this.autoRotateSpeed=2,this.keys={LEFT:"ArrowLeft",UP:"ArrowUp",RIGHT:"ArrowRight",BOTTOM:"ArrowDown"},this.mouseButtons={LEFT:qi.ROTATE,MIDDLE:qi.DOLLY,RIGHT:qi.PAN},this.touches={ONE:Wi.ROTATE,TWO:Wi.DOLLY_PAN},this.target0=this.target.clone(),this.position0=this.object.position.clone(),this.zoom0=this.object.zoom,this._domElementKeyEvents=null,this._lastPosition=new w,this._lastQuaternion=new Pt,this._lastTargetPosition=new w,this._quat=new Pt().setFromUnitVectors(e.up,new w(0,1,0)),this._quatInverse=this._quat.clone().invert(),this._spherical=new Fc,this._sphericalDelta=new Fc,this._scale=1,this._panOffset=new w,this._rotateStart=new Q,this._rotateEnd=new Q,this._rotateDelta=new Q,this._panStart=new Q,this._panEnd=new Q,this._panDelta=new Q,this._dollyStart=new Q,this._dollyEnd=new Q,this._dollyDelta=new Q,this._dollyDirection=new w,this._mouse=new Q,this._performCursorZoom=!1,this._pointers=[],this._pointerPositions={},this._controlActive=!1,this._onPointerMove=D1.bind(this),this._onPointerDown=R1.bind(this),this._onPointerUp=I1.bind(this),this._onContextMenu=k1.bind(this),this._onMouseWheel=U1.bind(this),this._onKeyDown=O1.bind(this),this._onTouchStart=F1.bind(this),this._onTouchMove=z1.bind(this),this._onMouseDown=L1.bind(this),this._onMouseMove=N1.bind(this),this._interceptControlDown=B1.bind(this),this._interceptControlUp=V1.bind(this),this.domElement!==null&&this.connect(),this.update()}connect(){this.domElement.addEventListener("pointerdown",this._onPointerDown),this.domElement.addEventListener("pointercancel",this._onPointerUp),this.domElement.addEventListener("contextmenu",this._onContextMenu),this.domElement.addEventListener("wheel",this._onMouseWheel,{passive:!1}),this.domElement.getRootNode().addEventListener("keydown",this._interceptControlDown,{passive:!0,capture:!0}),this.domElement.style.touchAction="none"}disconnect(){this.domElement.removeEventListener("pointerdown",this._onPointerDown),this.domElement.removeEventListener("pointermove",this._onPointerMove),this.domElement.removeEventListener("pointerup",this._onPointerUp),this.domElement.removeEventListener("pointercancel",this._onPointerUp),this.domElement.removeEventListener("wheel",this._onMouseWheel),this.domElement.removeEventListener("contextmenu",this._onContextMenu),this.stopListenToKeyEvents(),this.domElement.getRootNode().removeEventListener("keydown",this._interceptControlDown,{capture:!0}),this.domElement.style.touchAction="auto"}dispose(){this.disconnect()}getPolarAngle(){return this._spherical.phi}getAzimuthalAngle(){return this._spherical.theta}getDistance(){return this.object.position.distanceTo(this.target)}listenToKeyEvents(e){e.addEventListener("keydown",this._onKeyDown),this._domElementKeyEvents=e}stopListenToKeyEvents(){this._domElementKeyEvents!==null&&(this._domElementKeyEvents.removeEventListener("keydown",this._onKeyDown),this._domElementKeyEvents=null)}saveState(){this.target0.copy(this.target),this.position0.copy(this.object.position),this.zoom0=this.object.zoom}reset(){this.target.copy(this.target0),this.object.position.copy(this.position0),this.object.zoom=this.zoom0,this.object.updateProjectionMatrix(),this.dispatchEvent(zc),this.update(),this.state=ct.NONE}update(e=null){const t=this.object.position;Rt.copy(t).sub(this.target),Rt.applyQuaternion(this._quat),this._spherical.setFromVector3(Rt),this.autoRotate&&this.state===ct.NONE&&this._rotateLeft(this._getAutoRotationAngle(e)),this.enableDamping?(this._spherical.theta+=this._sphericalDelta.theta*this.dampingFactor,this._spherical.phi+=this._sphericalDelta.phi*this.dampingFactor):(this._spherical.theta+=this._sphericalDelta.theta,this._spherical.phi+=this._sphericalDelta.phi);let n=this.minAzimuthAngle,i=this.maxAzimuthAngle;isFinite(n)&&isFinite(i)&&(n<-Math.PI?n+=Zt:n>Math.PI&&(n-=Zt),i<-Math.PI?i+=Zt:i>Math.PI&&(i-=Zt),n<=i?this._spherical.theta=Math.max(n,Math.min(i,this._spherical.theta)):this._spherical.theta=this._spherical.theta>(n+i)/2?Math.max(n,this._spherical.theta):Math.min(i,this._spherical.theta)),this._spherical.phi=Math.max(this.minPolarAngle,Math.min(this.maxPolarAngle,this._spherical.phi)),this._spherical.makeSafe(),this.enableDamping===!0?this.target.addScaledVector(this._panOffset,this.dampingFactor):this.target.add(this._panOffset),this.target.sub(this.cursor),this.target.clampLength(this.minTargetRadius,this.maxTargetRadius),this.target.add(this.cursor);let r=!1;if(this.zoomToCursor&&this._performCursorZoom||this.object.isOrthographicCamera)this._spherical.radius=this._clampDistance(this._spherical.radius);else{const o=this._spherical.radius;this._spherical.radius=this._clampDistance(this._spherical.radius*this._scale),r=o!=this._spherical.radius}if(Rt.setFromSpherical(this._spherical),Rt.applyQuaternion(this._quatInverse),t.copy(this.target).add(Rt),this.object.lookAt(this.target),this.enableDamping===!0?(this._sphericalDelta.theta*=1-this.dampingFactor,this._sphericalDelta.phi*=1-this.dampingFactor,this._panOffset.multiplyScalar(1-this.dampingFactor)):(this._sphericalDelta.set(0,0,0),this._panOffset.set(0,0,0)),this.zoomToCursor&&this._performCursorZoom){let o=null;if(this.object.isPerspectiveCamera){const a=Rt.length();o=this._clampDistance(a*this._scale);const l=a-o;this.object.position.addScaledVector(this._dollyDirection,l),this.object.updateMatrixWorld(),r=!!l}else if(this.object.isOrthographicCamera){const a=new w(this._mouse.x,this._mouse.y,0);a.unproject(this.object);const l=this.object.zoom;this.object.zoom=Math.max(this.minZoom,Math.min(this.maxZoom,this.object.zoom/this._scale)),this.object.updateProjectionMatrix(),r=l!==this.object.zoom;const c=new w(this._mouse.x,this._mouse.y,0);c.unproject(this.object),this.object.position.sub(c).add(a),this.object.updateMatrixWorld(),o=Rt.length()}else console.warn("WARNING: OrbitControls.js encountered an unknown camera type - zoom to cursor disabled."),this.zoomToCursor=!1;o!==null&&(this.screenSpacePanning?this.target.set(0,0,-1).transformDirection(this.object.matrix).multiplyScalar(o).add(this.object.position):(xr.origin.copy(this.object.position),xr.direction.set(0,0,-1).transformDirection(this.object.matrix),Math.abs(this.object.up.dot(xr.direction))<C1?this.object.lookAt(this.target):(kc.setFromNormalAndCoplanarPoint(this.object.up,this.target),xr.intersectPlane(kc,this.target))))}else if(this.object.isOrthographicCamera){const o=this.object.zoom;this.object.zoom=Math.max(this.minZoom,Math.min(this.maxZoom,this.object.zoom/this._scale)),o!==this.object.zoom&&(this.object.updateProjectionMatrix(),r=!0)}return this._scale=1,this._performCursorZoom=!1,r||this._lastPosition.distanceToSquared(this.object.position)>Bo||8*(1-this._lastQuaternion.dot(this.object.quaternion))>Bo||this._lastTargetPosition.distanceToSquared(this.target)>Bo?(this.dispatchEvent(zc),this._lastPosition.copy(this.object.position),this._lastQuaternion.copy(this.object.quaternion),this._lastTargetPosition.copy(this.target),!0):!1}_getAutoRotationAngle(e){return e!==null?Zt/60*this.autoRotateSpeed*e:Zt/60/60*this.autoRotateSpeed}_getZoomScale(e){const t=Math.abs(e*.01);return Math.pow(.95,this.zoomSpeed*t)}_rotateLeft(e){this._sphericalDelta.theta-=e}_rotateUp(e){this._sphericalDelta.phi-=e}_panLeft(e,t){Rt.setFromMatrixColumn(t,0),Rt.multiplyScalar(-e),this._panOffset.add(Rt)}_panUp(e,t){this.screenSpacePanning===!0?Rt.setFromMatrixColumn(t,1):(Rt.setFromMatrixColumn(t,0),Rt.crossVectors(this.object.up,Rt)),Rt.multiplyScalar(e),this._panOffset.add(Rt)}_pan(e,t){const n=this.domElement;if(this.object.isPerspectiveCamera){const i=this.object.position;Rt.copy(i).sub(this.target);let r=Rt.length();r*=Math.tan(this.object.fov/2*Math.PI/180),this._panLeft(2*e*r/n.clientHeight,this.object.matrix),this._panUp(2*t*r/n.clientHeight,this.object.matrix)}else this.object.isOrthographicCamera?(this._panLeft(e*(this.object.right-this.object.left)/this.object.zoom/n.clientWidth,this.object.matrix),this._panUp(t*(this.object.top-this.object.bottom)/this.object.zoom/n.clientHeight,this.object.matrix)):(console.warn("WARNING: OrbitControls.js encountered an unknown camera type - pan disabled."),this.enablePan=!1)}_dollyOut(e){this.object.isPerspectiveCamera||this.object.isOrthographicCamera?this._scale/=e:(console.warn("WARNING: OrbitControls.js encountered an unknown camera type - dolly/zoom disabled."),this.enableZoom=!1)}_dollyIn(e){this.object.isPerspectiveCamera||this.object.isOrthographicCamera?this._scale*=e:(console.warn("WARNING: OrbitControls.js encountered an unknown camera type - dolly/zoom disabled."),this.enableZoom=!1)}_updateZoomParameters(e,t){if(!this.zoomToCursor)return;this._performCursorZoom=!0;const n=this.domElement.getBoundingClientRect(),i=e-n.left,r=t-n.top,o=n.width,a=n.height;this._mouse.x=i/o*2-1,this._mouse.y=-(r/a)*2+1,this._dollyDirection.set(this._mouse.x,this._mouse.y,1).unproject(this.object).sub(this.object.position).normalize()}_clampDistance(e){return Math.max(this.minDistance,Math.min(this.maxDistance,e))}_handleMouseDownRotate(e){this._rotateStart.set(e.clientX,e.clientY)}_handleMouseDownDolly(e){this._updateZoomParameters(e.clientX,e.clientX),this._dollyStart.set(e.clientX,e.clientY)}_handleMouseDownPan(e){this._panStart.set(e.clientX,e.clientY)}_handleMouseMoveRotate(e){this._rotateEnd.set(e.clientX,e.clientY),this._rotateDelta.subVectors(this._rotateEnd,this._rotateStart).multiplyScalar(this.rotateSpeed);const t=this.domElement;this._rotateLeft(Zt*this._rotateDelta.x/t.clientHeight),this._rotateUp(Zt*this._rotateDelta.y/t.clientHeight),this._rotateStart.copy(this._rotateEnd),this.update()}_handleMouseMoveDolly(e){this._dollyEnd.set(e.clientX,e.clientY),this._dollyDelta.subVectors(this._dollyEnd,this._dollyStart),this._dollyDelta.y>0?this._dollyOut(this._getZoomScale(this._dollyDelta.y)):this._dollyDelta.y<0&&this._dollyIn(this._getZoomScale(this._dollyDelta.y)),this._dollyStart.copy(this._dollyEnd),this.update()}_handleMouseMovePan(e){this._panEnd.set(e.clientX,e.clientY),this._panDelta.subVectors(this._panEnd,this._panStart).multiplyScalar(this.panSpeed),this._pan(this._panDelta.x,this._panDelta.y),this._panStart.copy(this._panEnd),this.update()}_handleMouseWheel(e){this._updateZoomParameters(e.clientX,e.clientY),e.deltaY<0?this._dollyIn(this._getZoomScale(e.deltaY)):e.deltaY>0&&this._dollyOut(this._getZoomScale(e.deltaY)),this.update()}_handleKeyDown(e){let t=!1;switch(e.code){case this.keys.UP:e.ctrlKey||e.metaKey||e.shiftKey?this._rotateUp(Zt*this.rotateSpeed/this.domElement.clientHeight):this._pan(0,this.keyPanSpeed),t=!0;break;case this.keys.BOTTOM:e.ctrlKey||e.metaKey||e.shiftKey?this._rotateUp(-Zt*this.rotateSpeed/this.domElement.clientHeight):this._pan(0,-this.keyPanSpeed),t=!0;break;case this.keys.LEFT:e.ctrlKey||e.metaKey||e.shiftKey?this._rotateLeft(Zt*this.rotateSpeed/this.domElement.clientHeight):this._pan(this.keyPanSpeed,0),t=!0;break;case this.keys.RIGHT:e.ctrlKey||e.metaKey||e.shiftKey?this._rotateLeft(-Zt*this.rotateSpeed/this.domElement.clientHeight):this._pan(-this.keyPanSpeed,0),t=!0;break}t&&(e.preventDefault(),this.update())}_handleTouchStartRotate(e){if(this._pointers.length===1)this._rotateStart.set(e.pageX,e.pageY);else{const t=this._getSecondPointerPosition(e),n=.5*(e.pageX+t.x),i=.5*(e.pageY+t.y);this._rotateStart.set(n,i)}}_handleTouchStartPan(e){if(this._pointers.length===1)this._panStart.set(e.pageX,e.pageY);else{const t=this._getSecondPointerPosition(e),n=.5*(e.pageX+t.x),i=.5*(e.pageY+t.y);this._panStart.set(n,i)}}_handleTouchStartDolly(e){const t=this._getSecondPointerPosition(e),n=e.pageX-t.x,i=e.pageY-t.y,r=Math.sqrt(n*n+i*i);this._dollyStart.set(0,r)}_handleTouchStartDollyPan(e){this.enableZoom&&this._handleTouchStartDolly(e),this.enablePan&&this._handleTouchStartPan(e)}_handleTouchStartDollyRotate(e){this.enableZoom&&this._handleTouchStartDolly(e),this.enableRotate&&this._handleTouchStartRotate(e)}_handleTouchMoveRotate(e){if(this._pointers.length==1)this._rotateEnd.set(e.pageX,e.pageY);else{const n=this._getSecondPointerPosition(e),i=.5*(e.pageX+n.x),r=.5*(e.pageY+n.y);this._rotateEnd.set(i,r)}this._rotateDelta.subVectors(this._rotateEnd,this._rotateStart).multiplyScalar(this.rotateSpeed);const t=this.domElement;this._rotateLeft(Zt*this._rotateDelta.x/t.clientHeight),this._rotateUp(Zt*this._rotateDelta.y/t.clientHeight),this._rotateStart.copy(this._rotateEnd)}_handleTouchMovePan(e){if(this._pointers.length===1)this._panEnd.set(e.pageX,e.pageY);else{const t=this._getSecondPointerPosition(e),n=.5*(e.pageX+t.x),i=.5*(e.pageY+t.y);this._panEnd.set(n,i)}this._panDelta.subVectors(this._panEnd,this._panStart).multiplyScalar(this.panSpeed),this._pan(this._panDelta.x,this._panDelta.y),this._panStart.copy(this._panEnd)}_handleTouchMoveDolly(e){const t=this._getSecondPointerPosition(e),n=e.pageX-t.x,i=e.pageY-t.y,r=Math.sqrt(n*n+i*i);this._dollyEnd.set(0,r),this._dollyDelta.set(0,Math.pow(this._dollyEnd.y/this._dollyStart.y,this.zoomSpeed)),this._dollyOut(this._dollyDelta.y),this._dollyStart.copy(this._dollyEnd);const o=(e.pageX+t.x)*.5,a=(e.pageY+t.y)*.5;this._updateZoomParameters(o,a)}_handleTouchMoveDollyPan(e){this.enableZoom&&this._handleTouchMoveDolly(e),this.enablePan&&this._handleTouchMovePan(e)}_handleTouchMoveDollyRotate(e){this.enableZoom&&this._handleTouchMoveDolly(e),this.enableRotate&&this._handleTouchMoveRotate(e)}_addPointer(e){this._pointers.push(e.pointerId)}_removePointer(e){delete this._pointerPositions[e.pointerId];for(let t=0;t<this._pointers.length;t++)if(this._pointers[t]==e.pointerId){this._pointers.splice(t,1);return}}_isTrackingPointer(e){for(let t=0;t<this._pointers.length;t++)if(this._pointers[t]==e.pointerId)return!0;return!1}_trackPointer(e){let t=this._pointerPositions[e.pointerId];t===void 0&&(t=new Q,this._pointerPositions[e.pointerId]=t),t.set(e.pageX,e.pageY)}_getSecondPointerPosition(e){const t=e.pointerId===this._pointers[0]?this._pointers[1]:this._pointers[0];return this._pointerPositions[t]}_customWheelEvent(e){const t=e.deltaMode,n={clientX:e.clientX,clientY:e.clientY,deltaY:e.deltaY};switch(t){case 1:n.deltaY*=16;break;case 2:n.deltaY*=100;break}return e.ctrlKey&&!this._controlActive&&(n.deltaY*=10),n}}function R1(s){this.enabled!==!1&&(this._pointers.length===0&&(this.domElement.setPointerCapture(s.pointerId),this.domElement.addEventListener("pointermove",this._onPointerMove),this.domElement.addEventListener("pointerup",this._onPointerUp)),!this._isTrackingPointer(s)&&(this._addPointer(s),s.pointerType==="touch"?this._onTouchStart(s):this._onMouseDown(s)))}function D1(s){this.enabled!==!1&&(s.pointerType==="touch"?this._onTouchMove(s):this._onMouseMove(s))}function I1(s){switch(this._removePointer(s),this._pointers.length){case 0:this.domElement.releasePointerCapture(s.pointerId),this.domElement.removeEventListener("pointermove",this._onPointerMove),this.domElement.removeEventListener("pointerup",this._onPointerUp),this.dispatchEvent(Qh),this.state=ct.NONE;break;case 1:const e=this._pointers[0],t=this._pointerPositions[e];this._onTouchStart({pointerId:e,pageX:t.x,pageY:t.y});break}}function L1(s){let e;switch(s.button){case 0:e=this.mouseButtons.LEFT;break;case 1:e=this.mouseButtons.MIDDLE;break;case 2:e=this.mouseButtons.RIGHT;break;default:e=-1}switch(e){case qi.DOLLY:if(this.enableZoom===!1)return;this._handleMouseDownDolly(s),this.state=ct.DOLLY;break;case qi.ROTATE:if(s.ctrlKey||s.metaKey||s.shiftKey){if(this.enablePan===!1)return;this._handleMouseDownPan(s),this.state=ct.PAN}else{if(this.enableRotate===!1)return;this._handleMouseDownRotate(s),this.state=ct.ROTATE}break;case qi.PAN:if(s.ctrlKey||s.metaKey||s.shiftKey){if(this.enableRotate===!1)return;this._handleMouseDownRotate(s),this.state=ct.ROTATE}else{if(this.enablePan===!1)return;this._handleMouseDownPan(s),this.state=ct.PAN}break;default:this.state=ct.NONE}this.state!==ct.NONE&&this.dispatchEvent(ul)}function N1(s){switch(this.state){case ct.ROTATE:if(this.enableRotate===!1)return;this._handleMouseMoveRotate(s);break;case ct.DOLLY:if(this.enableZoom===!1)return;this._handleMouseMoveDolly(s);break;case ct.PAN:if(this.enablePan===!1)return;this._handleMouseMovePan(s);break}}function U1(s){this.enabled===!1||this.enableZoom===!1||this.state!==ct.NONE||(s.preventDefault(),this.dispatchEvent(ul),this._handleMouseWheel(this._customWheelEvent(s)),this.dispatchEvent(Qh))}function O1(s){this.enabled===!1||this.enablePan===!1||this._handleKeyDown(s)}function F1(s){switch(this._trackPointer(s),this._pointers.length){case 1:switch(this.touches.ONE){case Wi.ROTATE:if(this.enableRotate===!1)return;this._handleTouchStartRotate(s),this.state=ct.TOUCH_ROTATE;break;case Wi.PAN:if(this.enablePan===!1)return;this._handleTouchStartPan(s),this.state=ct.TOUCH_PAN;break;default:this.state=ct.NONE}break;case 2:switch(this.touches.TWO){case Wi.DOLLY_PAN:if(this.enableZoom===!1&&this.enablePan===!1)return;this._handleTouchStartDollyPan(s),this.state=ct.TOUCH_DOLLY_PAN;break;case Wi.DOLLY_ROTATE:if(this.enableZoom===!1&&this.enableRotate===!1)return;this._handleTouchStartDollyRotate(s),this.state=ct.TOUCH_DOLLY_ROTATE;break;default:this.state=ct.NONE}break;default:this.state=ct.NONE}this.state!==ct.NONE&&this.dispatchEvent(ul)}function z1(s){switch(this._trackPointer(s),this.state){case ct.TOUCH_ROTATE:if(this.enableRotate===!1)return;this._handleTouchMoveRotate(s),this.update();break;case ct.TOUCH_PAN:if(this.enablePan===!1)return;this._handleTouchMovePan(s),this.update();break;case ct.TOUCH_DOLLY_PAN:if(this.enableZoom===!1&&this.enablePan===!1)return;this._handleTouchMoveDollyPan(s),this.update();break;case ct.TOUCH_DOLLY_ROTATE:if(this.enableZoom===!1&&this.enableRotate===!1)return;this._handleTouchMoveDollyRotate(s),this.update();break;default:this.state=ct.NONE}}function k1(s){this.enabled!==!1&&s.preventDefault()}function B1(s){s.key==="Control"&&(this._controlActive=!0,this.domElement.getRootNode().addEventListener("keyup",this._interceptControlUp,{passive:!0,capture:!0}))}function V1(s){s.key==="Control"&&(this._controlActive=!1,this.domElement.getRootNode().removeEventListener("keyup",this._interceptControlUp,{passive:!0,capture:!0}))}class H1{context=null;master=null;musicGain=null;musicTimer=null;musicStep=0;enabled;constructor(e){this.enabled=e}resume(){if(this.enabled){if(!this.context){const e=window.AudioContext||window.webkitAudioContext;if(!e){this.enabled=!1;return}this.context=new e,this.master=this.context.createGain(),this.master.gain.value=.35,this.master.connect(this.context.destination),this.musicGain=this.context.createGain(),this.musicGain.gain.value=.18,this.musicGain.connect(this.master)}this.context.state==="suspended"&&this.context.resume()}}tone(e,t,n={}){if(!this.enabled||!this.context||!this.master)return;const i=this.context.currentTime,r=this.context.createOscillator(),o=this.context.createGain();r.type=n.type||"sine",r.frequency.setValueAtTime(e,i),n.slideTo&&r.frequency.exponentialRampToValueAtTime(Math.max(20,n.slideTo),i+t),o.gain.setValueAtTime(1e-4,i),o.gain.exponentialRampToValueAtTime(n.gain??.25,i+.01),o.gain.exponentialRampToValueAtTime(1e-4,i+t),r.connect(o),o.connect(n.target??this.master),r.start(i),r.stop(i+t+.02)}noise(e,t=.2,n=900){if(!this.enabled||!this.context||!this.master)return;const i=this.context.currentTime,r=Math.max(1,Math.floor(this.context.sampleRate*e)),o=this.context.createBuffer(1,r,this.context.sampleRate),a=o.getChannelData(0);for(let u=0;u<r;u+=1)a[u]=(Math.random()*2-1)*(1-u/r);const l=this.context.createBufferSource();l.buffer=o;const c=this.context.createBiquadFilter();c.type="lowpass",c.frequency.value=n;const h=this.context.createGain();h.gain.value=t,l.connect(c),c.connect(h),h.connect(this.master),l.start(i)}chime(e){const t=e==="coffee"?520:e==="supply"?380:660;this.tone(t,.16,{type:"triangle",gain:.18}),window.setTimeout(()=>this.tone(t*1.5,.22,{type:"sine",gain:.16}),90)}footstep(e){this.noise(.09,e?.14:.09,e?1200:800)}laser(){this.tone(1200,.12,{type:"square",gain:.12,slideTo:240})}explosion(){this.noise(.5,.28,420),this.tone(90,.4,{type:"sawtooth",gain:.14,slideTo:40})}alarm(){this.tone(680,.5,{type:"square",gain:.1,slideTo:420})}warp(){this.tone(120,1.6,{type:"sawtooth",gain:.16,slideTo:1400}),this.noise(1.4,.16,2600)}playMusic(e){if(this.resume(),!this.enabled||!this.context||!this.musicGain)return;this.stopMusic(),this.musicStep=0;const t=320;this.musicTimer=window.setInterval(()=>{if(!this.context||!this.musicGain)return;const n=e[this.musicStep%e.length],i=this.musicStep%8<4?1:.5;this.tone(n*i,.32,{type:"triangle",gain:.22,target:this.musicGain}),this.musicStep%4===0&&this.tone(n*.5,.5,{type:"sine",gain:.3,target:this.musicGain}),this.musicStep+=1},t)}stopMusic(){this.musicTimer!==null&&(window.clearInterval(this.musicTimer),this.musicTimer=null)}dispose(){this.stopMusic(),this.context&&this.context.close(),this.context=null,this.master=null,this.musicGain=null}}const Fa=(s={})=>typeof s=="string"?{tag:s}:{tag:s.tag,owner:s.owner,part:s.part},yn=1e-5;function G1(s,e,t){const n=s.getAttribute("position"),i=s.index,r=Math.floor((i?.count??n.count)/3);if(r>(t.maxTriangles??1e6))throw new Error("Static collision triangle budget exceeded");const o=new Float32Array(r*9),a=Array.from({length:r},(d,f)=>f),l=new w;for(let d=0;d<r*3;d++){if(l.fromBufferAttribute(n,i?i.getX(d):d).applyMatrix4(e),!Number.isFinite(l.x+l.y+l.z))throw new Error("Non-finite collision geometry");o.set([l.x,l.y,l.z],d*3)}const c=Math.max(2,Math.min(64,t.leafSize??12)),h=(d,f)=>{const g=new Lt;for(let p=d;p<f;p++)for(let m=0;m<9;m+=3)l.fromArray(o,a[p]*9+m),g.expandByPoint(l);const x={bounds:g,start:d,end:f};if(f-d>c){const p=g.getSize(new w),m=p.x>=p.y&&p.x>=p.z?0:p.y>=p.z?1:2,_=S=>o[S*9+m]+o[S*9+m+3]+o[S*9+m+6],v=a.slice(d,f).sort((S,E)=>_(S)-_(E));for(let S=0;S<v.length;S++)a[d+S]=v[S];const M=d+f>>>1;x.left=h(d,M),x.right=h(M,f)}return x},u=h(0,r);return{kind:"mesh",bounds:u.bounds,metadata:Fa(t),vertices:o,order:a,tree:u,triangleCount:r,containment:t.containment??"union"}}function Br(s,e,t,n,i){if(s.y+e<=n.y+yn||s.y>=i.y-yn)return!1;const r=Math.max(n.x,Math.min(i.x,s.x))-s.x,o=Math.max(n.z,Math.min(i.z,s.z))-s.z;return r*r+o*o<t*t-yn*yn}function Bc(s,e,t){const n=[];for(let i=0;i<s.length;i++){const r=s[i],o=s[(i+1)%s.length],a=t?r.y>=e:r.y<=e,l=t?o.y>=e:o.y<=e;if(a&&n.push(r),a!==l){const c=(e-r.y)/(o.y-r.y);n.push({x:r.x+(o.x-r.x)*c,y:e,z:r.z+(o.z-r.z)*c})}}return n}function W1(s,e,t,n,i){let r=[];for(let c=0;c<9;c+=3)r.push({x:s[e+c],y:s[e+c+1],z:s[e+c+2]});if(r=Bc(Bc(r,t.y+yn,!0),t.y+n-yn,!1),!r.length)return!1;let o=!1,a=!1,l=0;for(let c=0;c<r.length;c++){const h=r[c],u=r[(c+1)%r.length],d=u.x-h.x,f=u.z-h.z,g=d*d+f*f,x=g?_t.clamp(((t.x-h.x)*d+(t.z-h.z)*f)/g,0,1):0,p=h.x+x*d-t.x,m=h.z+x*f-t.z;if(p*p+m*m<i*i-yn*yn)return!0;const _=d*(t.z-h.z)-f*(t.x-h.x);o||=_>1e-10,a||=_<-1e-10,l+=h.x*u.z-u.x*h.z}return Math.abs(l)>1e-10&&!(o&&a)}const Vc=new w,Hc=new w,Gc=new w;function eu(s,e,t,n,i){if(i.shapeTests++,!Br(e,t,n,s.bounds.min,s.bounds.max))return!1;if(s.kind==="cylinder"){const o=n+s.radius;return(e.x-s.center.x)**2+(e.z-s.center.z)**2<o*o-1e-10}if(s.kind==="obb"){const o=Math.cos(s.yaw),a=Math.sin(s.yaw),l=e.x-s.center.x,c=e.z-s.center.z;return Vc.set(o*l-a*c,e.y-s.center.y,a*l+o*c),Hc.copy(s.half).negate(),Gc.copy(s.half),Br(Vc,t,n,Hc,Gc)}const r=o=>{i.bvhNodes++;const a=o.bounds;if(e.x+n<a.min.x||e.x-n>a.max.x||e.z+n<a.min.z||e.z-n>a.max.z||e.y+t<=a.min.y+yn||e.y>=a.max.y-yn)return!1;if(o.left)return r(o.left)||r(o.right);for(let l=o.start;l<o.end;l++)if(i.triangleTests++,W1(s.vertices,s.order[l]*9,e,t,n))return!0;return!1};return r(s.tree)}function X1(s){if(s.containmentCache)return s.containmentCache;const e=s.triangleCount,t=new Int32Array(e),n=new Uint8Array(e);for(let h=0;h<e;h++)t[h]=h;const i=h=>{for(;t[h]!==h;)t[h]=t[t[h]],h=t[h];return h},r=new Map,o=new Map,a=h=>{const u=s.vertices,d=Math.round(u[h]*1e5)+","+Math.round(u[h+1]*1e5)+","+Math.round(u[h+2]*1e5);let f=r.get(d);return f===void 0&&(f=r.size,r.set(d,f)),f};for(let h=0;h<e;h++){const u=a(h*9),d=a(h*9+3),f=a(h*9+6);if(!(u===d||u===f||d===f)){n[h]=1;for(const[g,x]of[[u,d],[d,f],[f,u]]){const p=Math.min(g,x)+":"+Math.max(g,x),m=g<x?1:-1,_=o.get(p);_?(t[i(h)]=i(_.triangle),_.count++,_.balance+=m):o.set(p,{triangle:h,count:1,balance:m})}}}const l=new Int32Array(e),c=new Uint8Array(e);for(let h=0;h<e;h++)l[h]=n[h]?i(h):-1,n[h]&&(c[l[h]]=1);for(const h of o.values())(h.count%2!==0||h.balance!==0)&&(c[i(h.triangle)]=0);return s.containmentCache={components:l,closed:c},s.containmentCache}const Y1=[new w(1,.371,.193),new w(-.317,.719,-1),new w(.231,-1,.617),new w(-1,-.419,.827),new w(.613,.277,1),new w(.853,-.691,-.137)].map(s=>s.normalize());function q1(s,e,t){if(s.containment==="surface"||!s.bounds.containsPoint(e))return!1;const n=new w,i=new w,r=new w,o=new w,a=new w,l=new w,c=new w,h=[];for(const x of Y1){const p=new bi(e,x),m=[];let _=!1;const v=M=>{if(t.bvhNodes++,!!p.intersectsBox(M.bounds)){if(M.left){v(M.left),v(M.right);return}for(let S=M.start;S<M.end;S++){t.triangleTests++;const E=s.order[S],C=E*9;if(n.fromArray(s.vertices,C),i.fromArray(s.vertices,C+3),r.fromArray(s.vertices,C+6),!p.intersectTriangle(n,i,r,!1,o))continue;const z=o.distanceTo(e);if(z<yn)continue;if(cn.getBarycoord(o,n,i,r,c),Math.min(Math.abs(c.x),Math.abs(c.y),Math.abs(c.z))<1e-9){_=!0;continue}a.subVectors(i,n).cross(l.subVectors(r,n));const T=a.dot(x);Math.abs(T)>1e-12&&m.push({triangle:E,distance:z,sign:Math.sign(T)})}}};if(v(s.tree),!_){if(!m.length)return!1;if(h.push(m),h.length===2)break}}if(!h.length)return!1;const{components:u,closed:d}=X1(s);let f,g=0;for(const x of h){x.sort((m,_)=>m.distance-_.distance);const p=new Map;for(const m of x){const _=u[m.triangle];_<0||!d[_]||p.set(_,(p.get(_)??0)+m.sign)}if(s.containment==="winding"){const m=[...p.values()].reduce((_,v)=>_+v,0);if(!m||g&&Math.sign(m)!==g)return!1;g=Math.sign(m)}else{const m=new Set([...p].filter(([,_])=>_!==0).map(([_])=>_));if(f=f?new Set([...f].filter(_=>m.has(_))):m,!f.size)return!1}}return s.containment==="winding"?g!==0:!!f?.size}function j1(s,e,t,n){const i=new w,r=h=>h.containsPoint(e.origin)||!!(e.intersectBox(h,i)&&i.distanceTo(e.origin)<t-1e-4);if(!r(s.bounds))return!1;if(s.kind==="obb"){const h=new Fe().makeRotationY(s.yaw).setPosition(s.center).invert(),u=e.clone().applyMatrix4(h),d=new Lt(s.half.clone().negate(),s.half);return d.containsPoint(u.origin)||!!(u.intersectBox(d,i)&&i.distanceTo(u.origin)<t-1e-4)}if(s.kind==="cylinder"){const h=e.origin.x-s.center.x,u=e.origin.z-s.center.z,d=s.bounds.min.y,f=s.bounds.max.y;if(h*h+u*u<=s.radius**2&&e.origin.y>=d&&e.origin.y<=f)return!0;const g=e.direction.x**2+e.direction.z**2,x=2*(h*e.direction.x+u*e.direction.z),p=h*h+u*u-s.radius**2,m=x*x-4*g*p;if(g>1e-12&&m>=0)for(const _ of[(-x-Math.sqrt(m))/(2*g),(-x+Math.sqrt(m))/(2*g)]){const v=e.origin.y+e.direction.y*_;if(_>=0&&_<t-1e-4&&v>=d&&v<=f)return!0}if(Math.abs(e.direction.y)>1e-12)for(const _ of[d,f]){const v=(_-e.origin.y)/e.direction.y;if(v>=0&&v<t-1e-4&&(h+e.direction.x*v)**2+(u+e.direction.z*v)**2<=s.radius**2)return!0}return!1}const o=new w,a=new w,l=new w,c=h=>{if(n.bvhNodes++,!r(h.bounds))return!1;if(h.left)return c(h.left)||c(h.right);for(let u=h.start;u<h.end;u++){n.triangleTests++;const d=s.order[u]*9;if(o.fromArray(s.vertices,d),a.fromArray(s.vertices,d+3),l.fromArray(s.vertices,d+6),e.intersectTriangle(o,a,l,!1,i)&&i.distanceTo(e.origin)<t-1e-4)return!0}return!1};return c(s.tree)}const dl=.42,K1=1.78,Z1=1.15,J1=1.62,$1=1;class Q1{boxes=[];shapes=[];stats={shapeTests:0,triangleTests:0,bvhNodes:0};add(e,t,n){this.boxes.push({min:e,max:t,tag:n})}addBox(e){this.boxes.push(e)}addFromCenter(e,t,n){const i=t.clone().multiplyScalar(.5);this.add(e.clone().sub(i),e.clone().add(i),n)}query(e,t=[]){t.length=0;for(const n of this.boxes)Wc(n,e)&&t.push(n);return t}queryShapes(e,t=[]){t.length=0;for(const n of this.shapes)Wc(n.bounds,e,!0)&&t.push(n);return t}addCylinder(e,t,n,i={}){if(!(t>0&&n>0))throw new Error("Cylinder dimensions must be positive");const r=new w(t,n/2,t),o={kind:"cylinder",center:e.clone(),radius:t,height:n,bounds:new Lt(e.clone().sub(r),e.clone().add(r)),metadata:Fa(i)};return this.shapes.push(o),o}addOBB(e,t,n,i={}){if(Math.min(t.x,t.y,t.z)<=0)throw new Error("OBB dimensions must be positive");const r=t.clone().multiplyScalar(.5),o=Math.abs(Math.cos(n)),a=Math.abs(Math.sin(n)),l=new w(o*r.x+a*r.z,r.y,a*r.x+o*r.z),c={kind:"obb",center:e.clone(),half:r,yaw:n,bounds:new Lt(e.clone().sub(l),e.clone().add(l)),metadata:Fa(i)};return this.shapes.push(c),c}addStaticGeometry(e,t=new Fe,n={}){const i=G1(e,t,n);return this.shapes.push(i),i}addStaticMesh(e,t={},n={}){const i=typeof t=="string"?{...n,tag:t}:t,r=[];return e.updateWorldMatrix(!0,!0),e.traverseVisible(o=>{const a=o;if(!a.isMesh||a.userData.nonSolid)return;const l=Array.isArray(a.material)?a.material:[a.material];(i.filter?!i.filter(a):l.some(c=>c.transparent))||r.push(this.addStaticGeometry(a.geometry,a.matrixWorld,{...i,part:i.part??a.name,owner:i.owner??e.name}))}),r}removeShape(e){const t=this.shapes.indexOf(e);t>=0&&this.shapes.splice(t,1)}clearStatic(){this.shapes.length=0}clear(){this.clearStatic(),this.boxes.length=0}intersectsPlayer(e,t,n=dl){const i=new w(e.x,e.y+t*.5,e.z);return this.boxes.some(r=>Br(e,t,n,r.min,r.max))||this.shapes.some(r=>eu(r,e,t,n,this.stats)||r.kind==="mesh"&&q1(r,i,this.stats))}segmentBlocked(e,t,n){const i=t.clone().sub(e),r=i.length();if(r<1e-6)return!1;const o=new bi(e,i.divideScalar(r)),a=new w;for(const l of this.boxes){if(n&&(l.metadata?.owner===n||l.tag===n))continue;const c=new Lt(l.min,l.max);if(c.containsPoint(e)||o.intersectBox(c,a)&&a.distanceTo(e)<r-1e-4)return!0}return this.shapes.some(l=>(!n||l.metadata.owner!==n)&&j1(l,o,r,this.stats))}}function Wc(s,e,t=!1){return t?s.max.x>=e.min.x&&s.min.x<=e.max.x&&s.max.y>=e.min.y&&s.min.y<=e.max.y&&s.max.z>=e.min.z&&s.min.z<=e.max.z:s.max.x>e.min.x&&s.min.x<e.max.x&&s.max.y>e.min.y&&s.min.y<e.max.y&&s.max.z>e.min.z&&s.min.z<e.max.z}function Nn(s,e,t,n,i){if(!i)return!1;const r=e[n],o=r+i,a=dl,l=new w(e.x-a,e.y,e.z-a),c=new w(e.x+a,e.y+t,e.z+a);i<0?l[n]+=i:c[n]+=i;const h=s.query({min:l,max:c}),u=s.queryShapes({min:l,max:c});if(!h.length&&!u.length)return e[n]=o,!1;const d=()=>h.some(x=>Br(e,t,a,x.min,x.max))||u.some(x=>eu(x,e,t,a,s.stats)),f=Math.max(1,Math.ceil(Math.abs(i)/(a/5)));let g=r;for(let x=1;x<=f;x++){if(e[n]=r+i*x/f,d()){let p=e[n];for(let m=0;m<14;m++)e[n]=(g+p)*.5,d()?p=e[n]:g=e[n];return e[n]=g,!0}g=e[n]}return!1}function ev(s,e,t,n){s.stats.shapeTests=s.stats.triangleTests=s.stats.bvhNodes=0;const i=e.clone(),r={position:i,grounded:!1,hitCeiling:!1,collidedX:!1,collidedZ:!1},o=e.clone(),a=n.y<=0&&Nn(s,o,t,"y",-.12);if(r.collidedX=Nn(s,i,t,"x",n.x),r.collidedZ=Nn(s,i,t,"z",n.z),a&&(r.collidedX||r.collidedZ)){const c=e.clone();if(!Nn(s,c,t,"y",.55)){const h=Nn(s,c,t,"x",n.x),u=Nn(s,c,t,"z",n.z);!h&&!u&&Nn(s,c,t,"y",-.55-.12)&&c.y>=e.y-.12&&(i.copy(c),r.collidedX=r.collidedZ=!1)}}const l=Nn(s,i,t,"y",n.y);if(r.grounded=l&&n.y<0,r.hitCeiling=l&&n.y>0,n.y<=0&&!r.grounded){const c=i.clone();Nn(s,c,t,"y",0-(a?.12:.002))&&(i.y=c.y,r.grounded=!0)}return r}function za(s,e,t,n){const i=s.createLinearGradient(0,e,0,e+t);if(!i)return n[0][1];for(const[r,o]of n)i.addColorStop(r,o);return i}function Vo(s,e,t,n,i,r){s.beginPath(),s.moveTo(e+r,t),s.lineTo(e+n-r,t),s.lineTo(e+n,t+r),s.lineTo(e+n,t+i-r),s.lineTo(e+n-r,t+i),s.lineTo(e+r,t+i),s.lineTo(e,t+i-r),s.lineTo(e,t+r),s.closePath()}function fl(s,e,t={}){const{x:n,y:i,w:r,h:o}=e,a=Math.max(2,o*.055),l=Math.min(9,o*.105),c=(t.hovered||t.selected)&&!t.disabled;s.save(),s.fillStyle="#030912",s.fillRect(n,i,r,o);const h=za(s,i,o,[[0,t.disabled?"#71818a":c?"#e0c887":"#aeb9b9"],[.2,c?"#8e713b":"#586970"],[.52,"#223344"],[.86,"#344456"],[1,c?"#bda05d":"#74848c"]]);s.fillStyle=h,Vo(s,n+1,i+1,r-2,o-2,l),s.fill();const u={x:n+a,y:i+a,w:r-a*2,h:o-a*2},d=za(s,i+a,o-a*2,[[0,t.disabled?"#15202a":t.pressed?"#030913":"#12305a"],[.3,"#061323"],[.72,c?"#12355d":"#07172c"],[1,c?"#25588b":"#123461"]]);s.fillStyle=d,Vo(s,u.x,u.y,u.w,u.h,l*.55),s.fill(),s.lineWidth=Math.max(1,o*.014),s.strokeStyle=t.disabled?"#577184":c?"#f1d28a":"#639bd5",s.stroke(),s.strokeStyle=t.disabled?"#2d465c":c?"#bce5ff":"#244f9a",s.lineWidth=Math.max(1,a*.24),Vo(s,u.x+2,u.y+2,u.w-4,u.h-4,l*.45),s.stroke();const f=Math.min(r*.09,o*.2);for(const g of[-1,1])for(const x of[-1,1]){const p=g<0?n+a*.65:n+r-a*.65,m=x<0?i+a*.65:i+o-a*.65;s.beginPath(),s.moveTo(p-g*f,m),s.lineTo(p-g*a,m),s.lineTo(p,m-x*a),s.lineTo(p,m-x*f),s.lineTo(p-g*a*.6,m-x*a*1.6),s.lineTo(p-g*f,m-x*a*.6),s.closePath(),s.fillStyle=t.disabled?"#73828b":c?"#e9cf91":"#b6b9ae",s.fill()}t.danger&&(s.fillStyle=t.disabled?"#766959":"#d49b62",s.fillRect(n+r*.38,i+o-a*.7,r*.24,Math.max(1,a*.3))),s.restore()}function tu(s,e){const{x:t,y:n,w:i,h:r}=e;s.save(),s.fillStyle="#071423",s.fillRect(t,n,i,r);const o=za(s,n,r*.23,[[0,"#d2c5a1"],[.3,"#84775c"],[.65,"#484a45"],[1,"#202f40"]]);for(const a of[-1,1])s.save(),s.translate(a<0?t:t+i,n),s.scale(a<0?1:-1,1),s.beginPath(),s.moveTo(0,r*.21),s.lineTo(0,r*.03),s.lineTo(i*.1,r*.03),s.quadraticCurveTo(i*.15,r*.025,i*.18,r*.1),s.lineTo(i*.46,r*.1),s.lineTo(i*.43,r*.17),s.lineTo(i*.16,r*.17),s.lineTo(i*.13,r*.21),s.closePath(),s.fillStyle=o,s.fill(),s.strokeStyle="#92b1c8",s.lineWidth=Math.max(1,r*.012),s.stroke(),s.restore();s.fillStyle="#477ba7",s.fillRect(t+6,n+r-3,i-12,1),s.fillStyle="#958768",s.fillRect(t+i*.35,n+r-2,i*.3,1);for(const a of[t+10,t+i-10])s.fillStyle="#14395c",s.fillRect(a-4,n+r*.4,8,r*.22),s.fillStyle="#78b8e8",s.fillRect(a-1,n+r*.44,2,r*.14);s.restore()}const Rr=Object.freeze({armour:9864027,armourEdge:12167808,structure:2438204,deck:2502969,recess:1055010,energy:2653667,energyCore:6667775,glass:4351378,bronze:5787453}),nu=Object.freeze({frame:Rr.armour,body:Rr.recess,energy:Rr.energy,text:"#e5e9df"});class tv{constructor(e,t=nu){this.theme=t,this.material.color.setHex(t.frame),this.dark.color.setHex(t.body),this.glow.color.setHex(t.energy),this.root=e,e.replaceChildren(),this.group.name="three-dimensional-flight-instruments",this.group.renderOrder=1e3;for(const i of[this.material,this.dark,this.glow])i.depthTest=!1,i.depthWrite=!1,i.transparent=!0;this.group.add(this.instrument,this.modal),this.modal.visible=!1,this.instrument.position.set(-1.38,-.98,-2.7),this.instrument.rotation.set(.14,.22,0),this.slab(this.instrument,1.34,.45,.08,0,0,0),this.status=this.label(this.instrument,"",1.25,.32,[0,0,.075],21),this.identity=this.label(this.group,"",1.3,.17,[-1.4,1.43,-2.8],25),this.prompt=this.label(this.group,"",1.85,.1,[0,-1.05,-3.1],18),this.notice=this.label(this.group,"",2.05,.12,[0,-1.3,-3.3],18);const n=new ve(new qt(.09),this.glow);n.position.set(-.76,0,.06),this.instrument.add(n),this.crosshair=new ve(new at(.009,.0018,4,16),this.glow),this.crosshair.position.z=-1,this.group.add(this.crosshair),this.input=document.createElement("input"),this.input.className="text-capture",this.input.setAttribute("aria-label","三维控制台文字输入"),this.input.autocomplete="off",document.body.append(this.input),this.input.addEventListener("input",()=>this.onInput()),this.input.addEventListener("compositionstart",()=>this.composing=!0),this.input.addEventListener("compositionend",()=>{this.composing=!1,this.onInput()}),window.addEventListener("keydown",this.keydown,!0),window.addEventListener("mousedown",this.preserveEntryFocus,!0),window.addEventListener("focus",this.restoreEntryFocus),document.addEventListener("pointerlockchange",this.restoreEntryFocus)}root;group=new qe;camera=null;ray=new hl;material=new Ke({color:12558435,metalness:.65,roughness:.32});dark=new Ke({color:1056305,metalness:.45,roughness:.4});glow=new Ge({color:7003379});labels=[];switches=[];instrument=new qe;modal=new qe;modalLabels=[];status;prompt;notice;identity;crosshair;input;toastUntil=0;banner="";modalResolve=null;onInput=()=>{};accept=()=>{};composing=!1;textEntry=!1;entryField=null;selected=0;active=!1;lastMinigame="";get hasModal(){return this.active}attach(e){this.camera=e,e.add(this.group)}slab(e,t,n,i,r,o,a){const l=new De,c=Math.min(n*.12,.035);l.moveTo(-t/2+c,n/2),l.lineTo(t/2-c,n/2),l.lineTo(t/2,n/2-c),l.lineTo(t/2,-n/2+c),l.lineTo(t/2-c,-n/2),l.lineTo(-t/2+c,-n/2),l.lineTo(-t/2,-n/2+c),l.lineTo(-t/2,n/2-c),l.closePath();const h=new xt(l,{depth:i,bevelEnabled:!0,bevelThickness:.018,bevelSize:.018,bevelSegments:2,steps:1});h.translate(0,0,-i/2);const u=new ve(h,this.dark);u.position.set(r,o,a),e.add(u);const d=new ve(h.clone(),this.material);d.scale.set(1.08,1.22,.75),d.position.set(r,o,a-i*.35),e.add(d);const f=new ve(new lt(t*.6,.012,.018),this.glow);f.position.set(r,o-n*.38,a+i*.5+.008),e.add(f);for(const g of[-1,1]){const x=new ve(new qt(Math.min(.04,n*.12)),this.material);x.scale.set(.55,1.3,.35),x.position.set(r+g*t*.38,o,a+i*.5+.028),e.add(x)}return u}label(e,t,n,i,r,o=26,a=!1){const l=document.createElement("canvas");l.width=1024,l.height=Math.max(80,Math.round(1024*i/n));const c=new ss(l);c.colorSpace=Ft,c.generateMipmaps=!1,c.minFilter=Ct;const h=new ve(new Gt(n,i),new Ge({map:c,transparent:!0,depthTest:!a,depthWrite:!1,toneMapped:!1}));h.position.set(...r),e.add(h);const u={mesh:h,canvas:l,texture:c,text:"__initial__"};return h.userData.font=o,(a?this.modalLabels:this.labels).push(u),this.paint(u,t),u}paint(e,t){if(t===e.text)return;e.text=t,e.mesh.visible=!!t;const n=e.canvas.getContext("2d"),{width:i,height:r}=e.canvas;n.clearRect(0,0,i,r),n.fillStyle=this.theme.text,n.textAlign="center",n.textBaseline="middle";const o=t.split(`
`),a=Math.min(r/(o.length*1.35+.2),e.mesh.userData.font*4.5);n.font="500 "+a+'px "Microsoft YaHei", sans-serif',o.forEach((l,c)=>n.fillText(l,i/2,r/2+(c-(o.length-1)/2)*a*1.25,i-24)),e.texture.needsUpdate=!0}setShipIdentity(e){this.paint(this.identity,"◈  "+e),this.identity.mesh.visible=!1}setCrosshairVisible(e,t="dot"){this.crosshair.visible=e&&!this.active}showPrompt(e,t="E"){this.paint(this.prompt,e?"[ "+t+" ]  "+e:"")}setStatus(e){const t=(e??[]).slice(0,2).map(n=>n.replace(/ · [0-9]+ FPS/,""));this.paint(this.status,t.join(`
`))}setBanner(e,t="warn"){this.banner=e??"",performance.now()>this.toastUntil&&this.paint(this.notice,this.banner)}setMinigame(e){this.lastMinigame=e?[e.title,e.score,e.extra,e.hint].filter(Boolean).join(" · "):"",this.lastMinigame&&this.paint(this.notice,this.lastMinigame)}toast(e,t="info",n=3600){this.toastUntil=performance.now()+n,this.paint(this.notice,e)}menu(e,t,n=""){return this.open(e,n,t)}confirm(e){return this.open(e.title,e.body??"",[{label:e.cancelLabel??"取消",value:"cancel"},{label:e.confirmLabel??"确认",value:"ok",danger:e.danger}]).then(t=>t==="ok")}ask(e){const t=this.open(e.title,e.hint??"输入文字 · Enter 确认 · Esc 取消",[{label:"取消",value:"cancel"},{label:"保存铭文",value:"input"}],!0);this.input.value=e.value??"";const n=this.slab(this.modal,2.75,.45,.13,0,.1,.12);n.name="engraved-text-entry",this.entryField=n,this.selected=-1;const i=this.label(this.modal,"",2.6,.33,[0,.1,.235],32,!0),r=this.label(this.modal,"",2.8,.2,[0,-.3,.2],24,!0);return this.onInput=()=>this.paint(i,this.input.value+" ▏"),this.onInput(),this.accept=()=>{if(this.composing)return;const o=e.validate?.(this.input.value);if(o){this.paint(r,o),this.selected=-1,this.restoreEntryFocus();return}this.finish(this.input.value)},this.switches[1].action=this.accept,this.input.focus({preventScroll:!0}),this.input.select(),t}open(e,t,n,i=!1){this.finish(null),this.clearModal(),this.active=!0,this.modal.visible=!0,this.group.visible=!0,this.modal.position.set(0,0,-3.4),this.instrument.visible=!1,this.selected=0,this.textEntry=i,this.composing=!1;const r=new ve(new ft(.16,28,20),new Ge({color:2391525,transparent:!0,opacity:.32,wireframe:!0}));r.position.set(0,n.length>3?-.35:1,0),this.modal.add(r);for(const c of[.23,.29,.36]){const h=new ve(new at(c,.006,5,72),this.glow);h.position.copy(r.position),h.rotation.x=c*1.6,h.rotation.y=.3,this.modal.add(h)}this.label(this.modal,e,2.9,.22,[0,1.14,.04],27,!0),t&&this.label(this.modal,t,3.05,i?.28:.18,[0,i?.72:.83,.03],18,!0);const o=n.length>3,a=Math.ceil(n.length/2),l=Math.min(.31,1.55/Math.max(1,a-1));return n.forEach((c,h)=>{const u=o?h<a?-1:1:h===0?-1:1,d=o?h%a:0,f=o?u*1.04:u*.72,g=i?-.72:o?.51-d*l:-.45,x=new qe;x.position.set(f,g,o?-.08-Math.abs(d-(a-1)/2)*.04:0),x.rotation.y=-u*.09,this.modal.add(x);const p=o?1.32:1.2,m=o?Math.min(.245,l*.88):.245,_=C=>{const z=document.createElement("canvas");z.width=1024,z.height=Math.round(1024*m/p),fl(z.getContext("2d"),{x:0,y:0,w:z.width,h:z.height},{selected:C,danger:c.danger});const T=new ss(z);return T.colorSpace=Ft,T.generateMipmaps=!1,T.minFilter=Ct,T},v=_(!1),M=_(!0),S=new ve(new Gt(p,m),new Ge({map:v,transparent:!0,side:Dt,depthWrite:!1,toneMapped:!1}));if(x.add(S),this.label(x,c.label,p*.82,Math.min(.105,m*.55),[0,0,.03],21,!0),o){const C=new hn([new w(u*.31,-.35,-.12),new w(u*.46,g,-.12),new w(f-u*p*.51,g,x.position.z)]),z=new ve(new Si(C,24,.002,3,!1),new Ge({color:2255799,transparent:!0,opacity:.22,depthWrite:!1}));this.modal.add(z)}const E=new ve(new Gt(p,m),new Ge({transparent:!0,opacity:0,depthWrite:!1,side:Dt}));E.position.z=.035,x.add(E),this.switches.push({mesh:S,hit:E,idle:v,highlight:M,action:()=>this.finish(c.value==="cancel"?null:c.value),base:0})}),this.label(this.modal,"选择投影符文 · Tab 切换 · Enter 激活 · Esc 返回",2.8,.11,[0,-1.43,.04],17,!0),this.modal.traverse(c=>{c.renderOrder=1e3;const h=c;if(h.material)for(const u of Array.isArray(h.material)?h.material:[h.material])u.depthTest=!1,u.depthWrite=!1}),document.pointerLockElement&&document.exitPointerLock(),new Promise(c=>this.modalResolve=c)}finish(e){const t=this.modalResolve;this.modalResolve=null,this.active=!1,this.modal.visible=!1,this.instrument.visible=!1,this.textEntry=!1,this.entryField=null,this.composing=!1,this.onInput=()=>{},this.accept=()=>{},this.input?.blur(),t?.(e)}clearModal(){const e=new Set([this.material,this.dark,this.glow]);this.modal.traverse(t=>{const n=t;if(n.geometry?.dispose(),n.material)for(const i of Array.isArray(n.material)?n.material:[n.material])e.has(i)||i.dispose()});for(const t of this.switches)t.idle.dispose(),t.highlight.dispose();for(const t of this.modalLabels)t.texture.dispose();this.modalLabels=[],this.modal.clear(),this.switches=[]}restoreEntryFocus=()=>{this.active&&this.textEntry&&!document.pointerLockElement&&this.input.focus({preventScroll:!0})};preserveEntryFocus=e=>{!this.active||!this.textEntry||e.button!==0||e.target?.tagName==="CANVAS"&&(e.preventDefault(),this.restoreEntryFocus())};keydown=e=>{if(this.active&&(e.stopPropagation(),!(e.isComposing||this.composing||e.keyCode===229))){if(e.key==="Escape"){e.preventDefault(),e.stopImmediatePropagation(),this.finish(null);return}if(e.key==="Tab"){e.preventDefault(),e.stopImmediatePropagation();const t=this.switches.length+(this.textEntry?1:0),n=this.textEntry?1:0;this.selected=(this.selected+n+(e.shiftKey?-1:1)+t)%t-n;return}if(e.key==="Enter"){if(e.preventDefault(),e.stopImmediatePropagation(),e.repeat)return;this.textEntry&&this.selected===-1?this.accept():this.switches[this.selected]?.action()}else this.textEntry&&(this.selected=-1,this.restoreEntryFocus())}};update(e,t){if(performance.now()>this.toastUntil&&this.paint(this.notice,this.lastMinigame||this.banner),!this.camera)return;const n=Math.tan(_t.degToRad(this.camera.fov/2))*2.7*this.camera.aspect;if(this.instrument.position.x=-Math.max(0,Math.min(1.38,n-.8)),this.identity.mesh.position.x=this.instrument.position.x,this.modal.scale.setScalar(Math.min(1,n/2.1)),this.instrument.visible=!1,!this.active)return;this.group.updateWorldMatrix(!0,!0),this.ray.setFromCamera(new Q(e.x,e.y),this.camera);const r=this.ray.intersectObjects(this.switches.map(o=>o.hit),!1)[0]?.object;this.switches.forEach((o,a)=>{const l=r===o.hit||!r&&a===this.selected;o.mesh.position.z=l?.008:o.base;const c=o.mesh.material;c.map=l?o.highlight:o.idle}),e.clicked&&(r?this.switches.find(o=>o.hit===r)?.action():this.entryField&&this.ray.intersectObject(this.entryField,!1).length&&(this.selected=-1,this.restoreEntryFocus()))}dispose(){this.finish(null),this.clearModal(),window.removeEventListener("keydown",this.keydown,!0),window.removeEventListener("mousedown",this.preserveEntryFocus,!0),window.removeEventListener("focus",this.restoreEntryFocus),document.removeEventListener("pointerlockchange",this.restoreEntryFocus),this.input.remove();for(const e of this.labels)e.texture.dispose();this.group.traverse(e=>{const t=e;if(t.geometry?.dispose(),t.material)for(const n of Array.isArray(t.material)?t.material:[t.material])n.dispose()}),this.group.removeFromParent()}}const iu={name:"CopyShader",uniforms:{tDiffuse:{value:null},opacity:{value:1}},vertexShader:`

		varying vec2 vUv;

		void main() {

			vUv = uv;
			gl_Position = projectionMatrix * modelViewMatrix * vec4( position, 1.0 );

		}`,fragmentShader:`

		uniform float opacity;

		uniform sampler2D tDiffuse;

		varying vec2 vUv;

		void main() {

			vec4 texel = texture2D( tDiffuse, vUv );
			gl_FragColor = opacity * texel;


		}`};class ls{constructor(){this.isPass=!0,this.enabled=!0,this.needsSwap=!0,this.clear=!1,this.renderToScreen=!1}setSize(){}render(){console.error("THREE.Pass: .render() must be implemented in derived pass.")}dispose(){}}const nv=new tl(-1,1,1,-1,0,1);class iv extends je{constructor(){super(),this.setAttribute("position",new Ae([-1,3,0,-1,-1,0,3,-1,0],3)),this.setAttribute("uv",new Ae([0,2,0,0,2,0],2))}}const sv=new iv;class pl{constructor(e){this._mesh=new ve(sv,e)}dispose(){this._mesh.geometry.dispose()}render(e){e.render(this._mesh,nv)}get material(){return this._mesh.material}set material(e){this._mesh.material=e}}class su extends ls{constructor(e,t){super(),this.textureID=t!==void 0?t:"tDiffuse",e instanceof gt?(this.uniforms=e.uniforms,this.material=e):e&&(this.uniforms=Is.clone(e.uniforms),this.material=new gt({name:e.name!==void 0?e.name:"unspecified",defines:Object.assign({},e.defines),uniforms:this.uniforms,vertexShader:e.vertexShader,fragmentShader:e.fragmentShader})),this.fsQuad=new pl(this.material)}render(e,t,n){this.uniforms[this.textureID]&&(this.uniforms[this.textureID].value=n.texture),this.fsQuad.material=this.material,this.renderToScreen?(e.setRenderTarget(null),this.fsQuad.render(e)):(e.setRenderTarget(t),this.clear&&e.clear(e.autoClearColor,e.autoClearDepth,e.autoClearStencil),this.fsQuad.render(e))}dispose(){this.material.dispose(),this.fsQuad.dispose()}}class Xc extends ls{constructor(e,t){super(),this.scene=e,this.camera=t,this.clear=!0,this.needsSwap=!1,this.inverse=!1}render(e,t,n){const i=e.getContext(),r=e.state;r.buffers.color.setMask(!1),r.buffers.depth.setMask(!1),r.buffers.color.setLocked(!0),r.buffers.depth.setLocked(!0);let o,a;this.inverse?(o=0,a=1):(o=1,a=0),r.buffers.stencil.setTest(!0),r.buffers.stencil.setOp(i.REPLACE,i.REPLACE,i.REPLACE),r.buffers.stencil.setFunc(i.ALWAYS,o,4294967295),r.buffers.stencil.setClear(a),r.buffers.stencil.setLocked(!0),e.setRenderTarget(n),this.clear&&e.clear(),e.render(this.scene,this.camera),e.setRenderTarget(t),this.clear&&e.clear(),e.render(this.scene,this.camera),r.buffers.color.setLocked(!1),r.buffers.depth.setLocked(!1),r.buffers.color.setMask(!0),r.buffers.depth.setMask(!0),r.buffers.stencil.setLocked(!1),r.buffers.stencil.setFunc(i.EQUAL,1,4294967295),r.buffers.stencil.setOp(i.KEEP,i.KEEP,i.KEEP),r.buffers.stencil.setLocked(!0)}}class rv extends ls{constructor(){super(),this.needsSwap=!1}render(e){e.state.buffers.stencil.setLocked(!1),e.state.buffers.stencil.setTest(!1)}}class ov{constructor(e,t){if(this.renderer=e,this._pixelRatio=e.getPixelRatio(),t===void 0){const n=e.getSize(new Q);this._width=n.width,this._height=n.height,t=new un(this._width*this._pixelRatio,this._height*this._pixelRatio,{type:bn}),t.texture.name="EffectComposer.rt1"}else this._width=t.width,this._height=t.height;this.renderTarget1=t,this.renderTarget2=t.clone(),this.renderTarget2.texture.name="EffectComposer.rt2",this.writeBuffer=this.renderTarget1,this.readBuffer=this.renderTarget2,this.renderToScreen=!0,this.passes=[],this.copyPass=new su(iu),this.copyPass.material.blending=kn,this.clock=new E1}swapBuffers(){const e=this.readBuffer;this.readBuffer=this.writeBuffer,this.writeBuffer=e}addPass(e){this.passes.push(e),e.setSize(this._width*this._pixelRatio,this._height*this._pixelRatio)}insertPass(e,t){this.passes.splice(t,0,e),e.setSize(this._width*this._pixelRatio,this._height*this._pixelRatio)}removePass(e){const t=this.passes.indexOf(e);t!==-1&&this.passes.splice(t,1)}isLastEnabledPass(e){for(let t=e+1;t<this.passes.length;t++)if(this.passes[t].enabled)return!1;return!0}render(e){e===void 0&&(e=this.clock.getDelta());const t=this.renderer.getRenderTarget();let n=!1;for(let i=0,r=this.passes.length;i<r;i++){const o=this.passes[i];if(o.enabled!==!1){if(o.renderToScreen=this.renderToScreen&&this.isLastEnabledPass(i),o.render(this.renderer,this.writeBuffer,this.readBuffer,e,n),o.needsSwap){if(n){const a=this.renderer.getContext(),l=this.renderer.state.buffers.stencil;l.setFunc(a.NOTEQUAL,1,4294967295),this.copyPass.render(this.renderer,this.writeBuffer,this.readBuffer,e),l.setFunc(a.EQUAL,1,4294967295)}this.swapBuffers()}Xc!==void 0&&(o instanceof Xc?n=!0:o instanceof rv&&(n=!1))}}this.renderer.setRenderTarget(t)}reset(e){if(e===void 0){const t=this.renderer.getSize(new Q);this._pixelRatio=this.renderer.getPixelRatio(),this._width=t.width,this._height=t.height,e=this.renderTarget1.clone(),e.setSize(this._width*this._pixelRatio,this._height*this._pixelRatio)}this.renderTarget1.dispose(),this.renderTarget2.dispose(),this.renderTarget1=e,this.renderTarget2=e.clone(),this.writeBuffer=this.renderTarget1,this.readBuffer=this.renderTarget2}setSize(e,t){this._width=e,this._height=t;const n=this._width*this._pixelRatio,i=this._height*this._pixelRatio;this.renderTarget1.setSize(n,i),this.renderTarget2.setSize(n,i);for(let r=0;r<this.passes.length;r++)this.passes[r].setSize(n,i)}setPixelRatio(e){this._pixelRatio=e,this.setSize(this._width,this._height)}dispose(){this.renderTarget1.dispose(),this.renderTarget2.dispose(),this.copyPass.dispose()}}class av extends ls{constructor(e,t,n=null,i=null,r=null){super(),this.scene=e,this.camera=t,this.overrideMaterial=n,this.clearColor=i,this.clearAlpha=r,this.clear=!0,this.clearDepth=!1,this.needsSwap=!1,this._oldClearColor=new Ne}render(e,t,n){const i=e.autoClear;e.autoClear=!1;let r,o;this.overrideMaterial!==null&&(o=this.scene.overrideMaterial,this.scene.overrideMaterial=this.overrideMaterial),this.clearColor!==null&&(e.getClearColor(this._oldClearColor),e.setClearColor(this.clearColor,e.getClearAlpha())),this.clearAlpha!==null&&(r=e.getClearAlpha(),e.setClearAlpha(this.clearAlpha)),this.clearDepth==!0&&e.clearDepth(),e.setRenderTarget(this.renderToScreen?null:n),this.clear===!0&&e.clear(e.autoClearColor,e.autoClearDepth,e.autoClearStencil),e.render(this.scene,this.camera),this.clearColor!==null&&e.setClearColor(this._oldClearColor),this.clearAlpha!==null&&e.setClearAlpha(r),this.overrideMaterial!==null&&(this.scene.overrideMaterial=o),e.autoClear=i}}const lv={uniforms:{tDiffuse:{value:null},luminosityThreshold:{value:1},smoothWidth:{value:1},defaultColor:{value:new Ne(0)},defaultOpacity:{value:0}},vertexShader:`

		varying vec2 vUv;

		void main() {

			vUv = uv;

			gl_Position = projectionMatrix * modelViewMatrix * vec4( position, 1.0 );

		}`,fragmentShader:`

		uniform sampler2D tDiffuse;
		uniform vec3 defaultColor;
		uniform float defaultOpacity;
		uniform float luminosityThreshold;
		uniform float smoothWidth;

		varying vec2 vUv;

		void main() {

			vec4 texel = texture2D( tDiffuse, vUv );

			float v = luminance( texel.xyz );

			vec4 outputColor = vec4( defaultColor.rgb, defaultOpacity );

			float alpha = smoothstep( luminosityThreshold, luminosityThreshold + smoothWidth, v );

			gl_FragColor = mix( outputColor, texel, alpha );

		}`};class os extends ls{constructor(e,t,n,i){super(),this.strength=t!==void 0?t:1,this.radius=n,this.threshold=i,this.resolution=e!==void 0?new Q(e.x,e.y):new Q(256,256),this.clearColor=new Ne(0,0,0),this.renderTargetsHorizontal=[],this.renderTargetsVertical=[],this.nMips=5;let r=Math.round(this.resolution.x/2),o=Math.round(this.resolution.y/2);this.renderTargetBright=new un(r,o,{type:bn}),this.renderTargetBright.texture.name="UnrealBloomPass.bright",this.renderTargetBright.texture.generateMipmaps=!1;for(let u=0;u<this.nMips;u++){const d=new un(r,o,{type:bn});d.texture.name="UnrealBloomPass.h"+u,d.texture.generateMipmaps=!1,this.renderTargetsHorizontal.push(d);const f=new un(r,o,{type:bn});f.texture.name="UnrealBloomPass.v"+u,f.texture.generateMipmaps=!1,this.renderTargetsVertical.push(f),r=Math.round(r/2),o=Math.round(o/2)}const a=lv;this.highPassUniforms=Is.clone(a.uniforms),this.highPassUniforms.luminosityThreshold.value=i,this.highPassUniforms.smoothWidth.value=.01,this.materialHighPassFilter=new gt({uniforms:this.highPassUniforms,vertexShader:a.vertexShader,fragmentShader:a.fragmentShader}),this.separableBlurMaterials=[];const l=[3,5,7,9,11];r=Math.round(this.resolution.x/2),o=Math.round(this.resolution.y/2);for(let u=0;u<this.nMips;u++)this.separableBlurMaterials.push(this.getSeperableBlurMaterial(l[u])),this.separableBlurMaterials[u].uniforms.invSize.value=new Q(1/r,1/o),r=Math.round(r/2),o=Math.round(o/2);this.compositeMaterial=this.getCompositeMaterial(this.nMips),this.compositeMaterial.uniforms.blurTexture1.value=this.renderTargetsVertical[0].texture,this.compositeMaterial.uniforms.blurTexture2.value=this.renderTargetsVertical[1].texture,this.compositeMaterial.uniforms.blurTexture3.value=this.renderTargetsVertical[2].texture,this.compositeMaterial.uniforms.blurTexture4.value=this.renderTargetsVertical[3].texture,this.compositeMaterial.uniforms.blurTexture5.value=this.renderTargetsVertical[4].texture,this.compositeMaterial.uniforms.bloomStrength.value=t,this.compositeMaterial.uniforms.bloomRadius.value=.1;const c=[1,.8,.6,.4,.2];this.compositeMaterial.uniforms.bloomFactors.value=c,this.bloomTintColors=[new w(1,1,1),new w(1,1,1),new w(1,1,1),new w(1,1,1),new w(1,1,1)],this.compositeMaterial.uniforms.bloomTintColors.value=this.bloomTintColors;const h=iu;this.copyUniforms=Is.clone(h.uniforms),this.blendMaterial=new gt({uniforms:this.copyUniforms,vertexShader:h.vertexShader,fragmentShader:h.fragmentShader,blending:Mn,depthTest:!1,depthWrite:!1,transparent:!0}),this.enabled=!0,this.needsSwap=!1,this._oldClearColor=new Ne,this.oldClearAlpha=1,this.basic=new Ge,this.fsQuad=new pl(null)}dispose(){for(let e=0;e<this.renderTargetsHorizontal.length;e++)this.renderTargetsHorizontal[e].dispose();for(let e=0;e<this.renderTargetsVertical.length;e++)this.renderTargetsVertical[e].dispose();this.renderTargetBright.dispose();for(let e=0;e<this.separableBlurMaterials.length;e++)this.separableBlurMaterials[e].dispose();this.compositeMaterial.dispose(),this.blendMaterial.dispose(),this.basic.dispose(),this.fsQuad.dispose()}setSize(e,t){let n=Math.round(e/2),i=Math.round(t/2);this.renderTargetBright.setSize(n,i);for(let r=0;r<this.nMips;r++)this.renderTargetsHorizontal[r].setSize(n,i),this.renderTargetsVertical[r].setSize(n,i),this.separableBlurMaterials[r].uniforms.invSize.value=new Q(1/n,1/i),n=Math.round(n/2),i=Math.round(i/2)}render(e,t,n,i,r){e.getClearColor(this._oldClearColor),this.oldClearAlpha=e.getClearAlpha();const o=e.autoClear;e.autoClear=!1,e.setClearColor(this.clearColor,0),r&&e.state.buffers.stencil.setTest(!1),this.renderToScreen&&(this.fsQuad.material=this.basic,this.basic.map=n.texture,e.setRenderTarget(null),e.clear(),this.fsQuad.render(e)),this.highPassUniforms.tDiffuse.value=n.texture,this.highPassUniforms.luminosityThreshold.value=this.threshold,this.fsQuad.material=this.materialHighPassFilter,e.setRenderTarget(this.renderTargetBright),e.clear(),this.fsQuad.render(e);let a=this.renderTargetBright;for(let l=0;l<this.nMips;l++)this.fsQuad.material=this.separableBlurMaterials[l],this.separableBlurMaterials[l].uniforms.colorTexture.value=a.texture,this.separableBlurMaterials[l].uniforms.direction.value=os.BlurDirectionX,e.setRenderTarget(this.renderTargetsHorizontal[l]),e.clear(),this.fsQuad.render(e),this.separableBlurMaterials[l].uniforms.colorTexture.value=this.renderTargetsHorizontal[l].texture,this.separableBlurMaterials[l].uniforms.direction.value=os.BlurDirectionY,e.setRenderTarget(this.renderTargetsVertical[l]),e.clear(),this.fsQuad.render(e),a=this.renderTargetsVertical[l];this.fsQuad.material=this.compositeMaterial,this.compositeMaterial.uniforms.bloomStrength.value=this.strength,this.compositeMaterial.uniforms.bloomRadius.value=this.radius,this.compositeMaterial.uniforms.bloomTintColors.value=this.bloomTintColors,e.setRenderTarget(this.renderTargetsHorizontal[0]),e.clear(),this.fsQuad.render(e),this.fsQuad.material=this.blendMaterial,this.copyUniforms.tDiffuse.value=this.renderTargetsHorizontal[0].texture,r&&e.state.buffers.stencil.setTest(!0),this.renderToScreen?(e.setRenderTarget(null),this.fsQuad.render(e)):(e.setRenderTarget(n),this.fsQuad.render(e)),e.setClearColor(this._oldClearColor,this.oldClearAlpha),e.autoClear=o}getSeperableBlurMaterial(e){const t=[];for(let n=0;n<e;n++)t.push(.39894*Math.exp(-.5*n*n/(e*e))/e);return new gt({defines:{KERNEL_RADIUS:e},uniforms:{colorTexture:{value:null},invSize:{value:new Q(.5,.5)},direction:{value:new Q(.5,.5)},gaussianCoefficients:{value:t}},vertexShader:`varying vec2 vUv;
				void main() {
					vUv = uv;
					gl_Position = projectionMatrix * modelViewMatrix * vec4( position, 1.0 );
				}`,fragmentShader:`#include <common>
				varying vec2 vUv;
				uniform sampler2D colorTexture;
				uniform vec2 invSize;
				uniform vec2 direction;
				uniform float gaussianCoefficients[KERNEL_RADIUS];

				void main() {
					float weightSum = gaussianCoefficients[0];
					vec3 diffuseSum = texture2D( colorTexture, vUv ).rgb * weightSum;
					for( int i = 1; i < KERNEL_RADIUS; i ++ ) {
						float x = float(i);
						float w = gaussianCoefficients[i];
						vec2 uvOffset = direction * invSize * x;
						vec3 sample1 = texture2D( colorTexture, vUv + uvOffset ).rgb;
						vec3 sample2 = texture2D( colorTexture, vUv - uvOffset ).rgb;
						diffuseSum += (sample1 + sample2) * w;
						weightSum += 2.0 * w;
					}
					gl_FragColor = vec4(diffuseSum/weightSum, 1.0);
				}`})}getCompositeMaterial(e){return new gt({defines:{NUM_MIPS:e},uniforms:{blurTexture1:{value:null},blurTexture2:{value:null},blurTexture3:{value:null},blurTexture4:{value:null},blurTexture5:{value:null},bloomStrength:{value:1},bloomFactors:{value:null},bloomTintColors:{value:null},bloomRadius:{value:0}},vertexShader:`varying vec2 vUv;
				void main() {
					vUv = uv;
					gl_Position = projectionMatrix * modelViewMatrix * vec4( position, 1.0 );
				}`,fragmentShader:`varying vec2 vUv;
				uniform sampler2D blurTexture1;
				uniform sampler2D blurTexture2;
				uniform sampler2D blurTexture3;
				uniform sampler2D blurTexture4;
				uniform sampler2D blurTexture5;
				uniform float bloomStrength;
				uniform float bloomRadius;
				uniform float bloomFactors[NUM_MIPS];
				uniform vec3 bloomTintColors[NUM_MIPS];

				float lerpBloomFactor(const in float factor) {
					float mirrorFactor = 1.2 - factor;
					return mix(factor, mirrorFactor, bloomRadius);
				}

				void main() {
					gl_FragColor = bloomStrength * ( lerpBloomFactor(bloomFactors[0]) * vec4(bloomTintColors[0], 1.0) * texture2D(blurTexture1, vUv) +
						lerpBloomFactor(bloomFactors[1]) * vec4(bloomTintColors[1], 1.0) * texture2D(blurTexture2, vUv) +
						lerpBloomFactor(bloomFactors[2]) * vec4(bloomTintColors[2], 1.0) * texture2D(blurTexture3, vUv) +
						lerpBloomFactor(bloomFactors[3]) * vec4(bloomTintColors[3], 1.0) * texture2D(blurTexture4, vUv) +
						lerpBloomFactor(bloomFactors[4]) * vec4(bloomTintColors[4], 1.0) * texture2D(blurTexture5, vUv) );
				}`})}}os.BlurDirectionX=new Q(1,0);os.BlurDirectionY=new Q(0,1);const cv={name:"OutputShader",uniforms:{tDiffuse:{value:null},toneMappingExposure:{value:1}},vertexShader:`
		precision highp float;

		uniform mat4 modelViewMatrix;
		uniform mat4 projectionMatrix;

		attribute vec3 position;
		attribute vec2 uv;

		varying vec2 vUv;

		void main() {

			vUv = uv;
			gl_Position = projectionMatrix * modelViewMatrix * vec4( position, 1.0 );

		}`,fragmentShader:`
	
		precision highp float;

		uniform sampler2D tDiffuse;

		#include <tonemapping_pars_fragment>
		#include <colorspace_pars_fragment>

		varying vec2 vUv;

		void main() {

			gl_FragColor = texture2D( tDiffuse, vUv );

			// tone mapping

			#ifdef LINEAR_TONE_MAPPING

				gl_FragColor.rgb = LinearToneMapping( gl_FragColor.rgb );

			#elif defined( REINHARD_TONE_MAPPING )

				gl_FragColor.rgb = ReinhardToneMapping( gl_FragColor.rgb );

			#elif defined( CINEON_TONE_MAPPING )

				gl_FragColor.rgb = CineonToneMapping( gl_FragColor.rgb );

			#elif defined( ACES_FILMIC_TONE_MAPPING )

				gl_FragColor.rgb = ACESFilmicToneMapping( gl_FragColor.rgb );

			#elif defined( AGX_TONE_MAPPING )

				gl_FragColor.rgb = AgXToneMapping( gl_FragColor.rgb );

			#elif defined( NEUTRAL_TONE_MAPPING )

				gl_FragColor.rgb = NeutralToneMapping( gl_FragColor.rgb );

			#endif

			// color space

			#ifdef SRGB_TRANSFER

				gl_FragColor = sRGBTransferOETF( gl_FragColor );

			#endif

		}`};class hv extends ls{constructor(){super();const e=cv;this.uniforms=Is.clone(e.uniforms),this.material=new M1({name:e.name,uniforms:this.uniforms,vertexShader:e.vertexShader,fragmentShader:e.fragmentShader}),this.fsQuad=new pl(this.material),this._outputColorSpace=null,this._toneMapping=null}render(e,t,n){this.uniforms.tDiffuse.value=n.texture,this.uniforms.toneMappingExposure.value=e.toneMappingExposure,(this._outputColorSpace!==e.outputColorSpace||this._toneMapping!==e.toneMapping)&&(this._outputColorSpace=e.outputColorSpace,this._toneMapping=e.toneMapping,this.material.defines={},nt.getTransfer(this._outputColorSpace)===ut&&(this.material.defines.SRGB_TRANSFER=""),this._toneMapping===uh?this.material.defines.LINEAR_TONE_MAPPING="":this._toneMapping===dh?this.material.defines.REINHARD_TONE_MAPPING="":this._toneMapping===fh?this.material.defines.CINEON_TONE_MAPPING="":this._toneMapping===Wr?this.material.defines.ACES_FILMIC_TONE_MAPPING="":this._toneMapping===ph?this.material.defines.AGX_TONE_MAPPING="":this._toneMapping===mh&&(this.material.defines.NEUTRAL_TONE_MAPPING=""),this.material.needsUpdate=!0),this.renderToScreen===!0?(e.setRenderTarget(null),this.fsQuad.render(e)):(e.setRenderTarget(t),this.clear&&e.clear(e.autoClearColor,e.autoClearDepth,e.autoClearStencil),this.fsQuad.render(e))}dispose(){this.material.dispose(),this.fsQuad.dispose()}}const uv={name:"FXAAShader",uniforms:{tDiffuse:{value:null},resolution:{value:new Q(1/1024,1/512)}},vertexShader:`

		varying vec2 vUv;

		void main() {

			vUv = uv;
			gl_Position = projectionMatrix * modelViewMatrix * vec4( position, 1.0 );

		}`,fragmentShader:`
		precision highp float;

		uniform sampler2D tDiffuse;

		uniform vec2 resolution;

		varying vec2 vUv;

		// FXAA 3.11 implementation by NVIDIA, ported to WebGL by Agost Biro (biro@archilogic.com)

		//----------------------------------------------------------------------------------
		// File:        es3-keplerFXAAassetsshaders/FXAA_DefaultES.frag
		// SDK Version: v3.00
		// Email:       gameworks@nvidia.com
		// Site:        http://developer.nvidia.com/
		//
		// Copyright (c) 2014-2015, NVIDIA CORPORATION. All rights reserved.
		//
		// Redistribution and use in source and binary forms, with or without
		// modification, are permitted provided that the following conditions
		// are met:
		//  * Redistributions of source code must retain the above copyright
		//    notice, this list of conditions and the following disclaimer.
		//  * Redistributions in binary form must reproduce the above copyright
		//    notice, this list of conditions and the following disclaimer in the
		//    documentation and/or other materials provided with the distribution.
		//  * Neither the name of NVIDIA CORPORATION nor the names of its
		//    contributors may be used to endorse or promote products derived
		//    from this software without specific prior written permission.
		//
		// THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS ''AS IS'' AND ANY
		// EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
		// IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
		// PURPOSE ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR
		// CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
		// EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
		// PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
		// PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY
		// OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
		// (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
		// OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
		//
		//----------------------------------------------------------------------------------

		#ifndef FXAA_DISCARD
			//
			// Only valid for PC OpenGL currently.
			// Probably will not work when FXAA_GREEN_AS_LUMA = 1.
			//
			// 1 = Use discard on pixels which don't need AA.
			//     For APIs which enable concurrent TEX+ROP from same surface.
			// 0 = Return unchanged color on pixels which don't need AA.
			//
			#define FXAA_DISCARD 0
		#endif

		/*--------------------------------------------------------------------------*/
		#define FxaaTexTop(t, p) texture2D(t, p, -100.0)
		#define FxaaTexOff(t, p, o, r) texture2D(t, p + (o * r), -100.0)
		/*--------------------------------------------------------------------------*/

		#define NUM_SAMPLES 5

		// assumes colors have premultipliedAlpha, so that the calculated color contrast is scaled by alpha
		float contrast( vec4 a, vec4 b ) {
			vec4 diff = abs( a - b );
			return max( max( max( diff.r, diff.g ), diff.b ), diff.a );
		}

		/*============================================================================

									FXAA3 QUALITY - PC

		============================================================================*/

		/*--------------------------------------------------------------------------*/
		vec4 FxaaPixelShader(
			vec2 posM,
			sampler2D tex,
			vec2 fxaaQualityRcpFrame,
			float fxaaQualityEdgeThreshold,
			float fxaaQualityinvEdgeThreshold
		) {
			vec4 rgbaM = FxaaTexTop(tex, posM);
			vec4 rgbaS = FxaaTexOff(tex, posM, vec2( 0.0, 1.0), fxaaQualityRcpFrame.xy);
			vec4 rgbaE = FxaaTexOff(tex, posM, vec2( 1.0, 0.0), fxaaQualityRcpFrame.xy);
			vec4 rgbaN = FxaaTexOff(tex, posM, vec2( 0.0,-1.0), fxaaQualityRcpFrame.xy);
			vec4 rgbaW = FxaaTexOff(tex, posM, vec2(-1.0, 0.0), fxaaQualityRcpFrame.xy);
			// . S .
			// W M E
			// . N .

			bool earlyExit = max( max( max(
					contrast( rgbaM, rgbaN ),
					contrast( rgbaM, rgbaS ) ),
					contrast( rgbaM, rgbaE ) ),
					contrast( rgbaM, rgbaW ) )
					< fxaaQualityEdgeThreshold;
			// . 0 .
			// 0 0 0
			// . 0 .

			#if (FXAA_DISCARD == 1)
				if(earlyExit) FxaaDiscard;
			#else
				if(earlyExit) return rgbaM;
			#endif

			float contrastN = contrast( rgbaM, rgbaN );
			float contrastS = contrast( rgbaM, rgbaS );
			float contrastE = contrast( rgbaM, rgbaE );
			float contrastW = contrast( rgbaM, rgbaW );

			float relativeVContrast = ( contrastN + contrastS ) - ( contrastE + contrastW );
			relativeVContrast *= fxaaQualityinvEdgeThreshold;

			bool horzSpan = relativeVContrast > 0.;
			// . 1 .
			// 0 0 0
			// . 1 .

			// 45 deg edge detection and corners of objects, aka V/H contrast is too similar
			if( abs( relativeVContrast ) < .3 ) {
				// locate the edge
				vec2 dirToEdge;
				dirToEdge.x = contrastE > contrastW ? 1. : -1.;
				dirToEdge.y = contrastS > contrastN ? 1. : -1.;
				// . 2 .      . 1 .
				// 1 0 2  ~=  0 0 1
				// . 1 .      . 0 .

				// tap 2 pixels and see which ones are "outside" the edge, to
				// determine if the edge is vertical or horizontal

				vec4 rgbaAlongH = FxaaTexOff(tex, posM, vec2( dirToEdge.x, -dirToEdge.y ), fxaaQualityRcpFrame.xy);
				float matchAlongH = contrast( rgbaM, rgbaAlongH );
				// . 1 .
				// 0 0 1
				// . 0 H

				vec4 rgbaAlongV = FxaaTexOff(tex, posM, vec2( -dirToEdge.x, dirToEdge.y ), fxaaQualityRcpFrame.xy);
				float matchAlongV = contrast( rgbaM, rgbaAlongV );
				// V 1 .
				// 0 0 1
				// . 0 .

				relativeVContrast = matchAlongV - matchAlongH;
				relativeVContrast *= fxaaQualityinvEdgeThreshold;

				if( abs( relativeVContrast ) < .3 ) { // 45 deg edge
					// 1 1 .
					// 0 0 1
					// . 0 1

					// do a simple blur
					return mix(
						rgbaM,
						(rgbaN + rgbaS + rgbaE + rgbaW) * .25,
						.4
					);
				}

				horzSpan = relativeVContrast > 0.;
			}

			if(!horzSpan) rgbaN = rgbaW;
			if(!horzSpan) rgbaS = rgbaE;
			// . 0 .      1
			// 1 0 1  ->  0
			// . 0 .      1

			bool pairN = contrast( rgbaM, rgbaN ) > contrast( rgbaM, rgbaS );
			if(!pairN) rgbaN = rgbaS;

			vec2 offNP;
			offNP.x = (!horzSpan) ? 0.0 : fxaaQualityRcpFrame.x;
			offNP.y = ( horzSpan) ? 0.0 : fxaaQualityRcpFrame.y;

			bool doneN = false;
			bool doneP = false;

			float nDist = 0.;
			float pDist = 0.;

			vec2 posN = posM;
			vec2 posP = posM;

			int iterationsUsedN = 0;
			int iterationsUsedP = 0;
			for( int i = 0; i < NUM_SAMPLES; i++ ) {

				float increment = float(i + 1);

				if(!doneN) {
					nDist += increment;
					posN = posM + offNP * nDist;
					vec4 rgbaEndN = FxaaTexTop(tex, posN.xy);
					doneN = contrast( rgbaEndN, rgbaM ) > contrast( rgbaEndN, rgbaN );
					iterationsUsedN = i;
				}

				if(!doneP) {
					pDist += increment;
					posP = posM - offNP * pDist;
					vec4 rgbaEndP = FxaaTexTop(tex, posP.xy);
					doneP = contrast( rgbaEndP, rgbaM ) > contrast( rgbaEndP, rgbaN );
					iterationsUsedP = i;
				}

				if(doneN || doneP) break;
			}


			if ( !doneP && !doneN ) return rgbaM; // failed to find end of edge

			float dist = min(
				doneN ? float( iterationsUsedN ) / float( NUM_SAMPLES - 1 ) : 1.,
				doneP ? float( iterationsUsedP ) / float( NUM_SAMPLES - 1 ) : 1.
			);

			// hacky way of reduces blurriness of mostly diagonal edges
			// but reduces AA quality
			dist = pow(dist, .5);

			dist = 1. - dist;

			return mix(
				rgbaM,
				rgbaN,
				dist * .5
			);
		}

		void main() {
			const float edgeDetectionQuality = .2;
			const float invEdgeDetectionQuality = 1. / edgeDetectionQuality;

			gl_FragColor = FxaaPixelShader(
				vUv,
				tDiffuse,
				resolution,
				edgeDetectionQuality, // [0,1] contrast needed, otherwise early discard
				invEdgeDetectionQuality
			);

		}
	`};function dv(){const t=new Uint16Array(524288),n=new w(-.55,.63,.55).normalize(),i=new w(.82,.25,-.52).normalize(),r=new w(.15,-.1,.98).normalize(),o=(l,c,h,u,d,f)=>{const g=l*u.x+c*u.y+h*u.z;if(g<=0)return 0;const x=Math.hypot(u.x,u.z),p=u.z/x,m=-u.x/x,_=u.y*m,v=u.z*p-u.x*m,M=-u.y*p,S=(l*p+h*m)/g/d,E=(l*_+c*v+h*M)/g/f;return Math.exp(-Math.pow(Math.abs(S),6)-Math.pow(Math.abs(E),6))};for(let l=0;l<256;l++){const c=(1-(l+.5)/256)*Math.PI,h=Math.cos(c),u=Math.sin(c);for(let d=0;d<512;d++){const f=(d+.5)/512*Math.PI*2,g=u*Math.cos(f),x=u*Math.sin(f),p=o(g,h,x,n,.58,.32)*1.55,m=o(g,h,x,i,.16,.9)*1.4,_=o(g,h,x,r,1.15,.32)*.24,v=.018+Math.max(0,h)*.045,M=Math.exp(-h*h*20)*.025,S=(l*512+d)*4;t[S]=Js.toHalfFloat(v*.65+M+p+m*.44+_*.56),t[S+1]=Js.toHalfFloat(v*.9+M*.8+p*.91+m*.72+_*.78),t[S+2]=Js.toHalfFloat(v*1.3+M*.7+p*.74+m+_),t[S+3]=Js.toHalfFloat(1)}}const a=new Gh(t,512,256,sn,bn);return a.name="ark-authored-hdr-radiance",a.mapping=Dr,a.colorSpace=Hn,a.minFilter=Ct,a.magFilter=Ct,a.generateMipmaps=!1,a.needsUpdate=!0,a}class fv{constructor(e,t,n,i="medium"){this.renderer=e,this.scene=t,this.camera=n,this.quality=i,this.previousEnvironment=t.environment,this.previousEnvironmentIntensity=t.environmentIntensity,this.previousEnvironmentRotation=t.environmentRotation.clone(),this.previousOutputColorSpace=e.outputColorSpace,this.previousToneMapping=e.toneMapping,this.previousExposure=e.toneMappingExposure,e.outputColorSpace=Ft,e.toneMapping=Wr,e.toneMappingExposure=.95;const r=dv(),o=new Ra(e);try{o.compileEquirectangularShader(),this.environment=o.fromEquirectangular(r)}finally{r.dispose(),o.dispose()}this.environment.texture.name="ark-specular-pmrem",t.environment=this.environment.texture,t.environmentIntensity=.72,t.environmentRotation.set(0,.35,0);const a=e.getSize(new Q);this.width=Math.max(1,a.x),this.height=Math.max(1,a.y),this.pixelRatio=e.getPixelRatio(),this.updateQuality(i)}environment;previousEnvironment;previousEnvironmentIntensity;previousEnvironmentRotation;previousOutputColorSpace;previousToneMapping;previousExposure;composer=null;bloom=null;fxaa=null;quality;width=1;height=1;pixelRatio=1;disposed=!1;updateQuality(e){if(this.disposed)return;const t=e!==this.quality;if(this.quality=e,e==="low"){this.disposeComposer();return}if(!this.composer||t){this.disposeComposer();const n=Math.min(this.renderer.capabilities.maxSamples,e==="high"?4:2),i=new un(this.width*this.pixelRatio,this.height*this.pixelRatio,{type:bn,format:sn,minFilter:Ct,magFilter:Ct,depthBuffer:!0,stencilBuffer:!1,samples:n});i.texture.name="ark-linear-hdr-output",this.composer=new ov(this.renderer,i),this.composer.addPass(new av(this.scene,this.camera)),this.bloom=new os(new Q(this.width,this.height),e==="high"?.3:.24,.44,1.1),this.composer.addPass(this.bloom),this.composer.addPass(new hv),n<2&&(this.fxaa=new su(uv),this.composer.addPass(this.fxaa)),this.resize(this.width,this.height,this.pixelRatio)}}resize(e,t,n=this.renderer.getPixelRatio()){this.disposed||(this.width=Math.max(1,Math.floor(e)),this.height=Math.max(1,Math.floor(t)),this.pixelRatio=Math.max(.25,n),this.composer?.setPixelRatio(this.pixelRatio),this.composer?.setSize(this.width,this.height),this.fxaa?.uniforms.resolution.value.set(1/(this.width*this.pixelRatio),1/(this.height*this.pixelRatio)))}render(e=0){this.disposed||(this.composer?this.composer.render(Math.min(Math.max(e,0),.1)):this.renderer.render(this.scene,this.camera))}disposeComposer(){if(this.composer){this.bloom?.materialHighPassFilter.dispose();for(const e of this.composer.passes)e.dispose();this.composer.dispose(),this.composer=null,this.bloom=null,this.fxaa=null}}dispose(){this.disposed||(this.disposed=!0,this.disposeComposer(),this.scene.environment===this.environment.texture&&(this.scene.environment=this.previousEnvironment,this.scene.environmentIntensity=this.previousEnvironmentIntensity,this.scene.environmentRotation.copy(this.previousEnvironmentRotation)),this.environment.dispose(),this.renderer.outputColorSpace=this.previousOutputColorSpace,this.renderer.toneMapping=this.previousToneMapping,this.renderer.toneMappingExposure=this.previousExposure)}}const Yc={ArrowUp:"up",ArrowDown:"down",ArrowLeft:"left",ArrowRight:"right"," ":"space"};class pv{keys=new Set;pointer={x:0,y:0,clientX:0,clientY:0,down:!1,clicked:!1,deltaX:0,deltaY:0,wheel:0};pressedThisFrame=new Set;pressedQueue=[];mode="world";locked=!1;textMode=!1;sensitivity=1;invertY=!1;element;listeners=[];onClickHandlers=[];constructor(e){this.element=e,this.bind()}on(e,t,n,i){e.addEventListener(t,n,i),this.listeners.push(()=>e.removeEventListener(t,n,i))}bind(){this.on(window,"keydown",e=>{if(this.textMode||this.mode==="menu"||document.querySelector("dialog[open]")||e.target?.closest('input, textarea, select, [contenteditable="true"], .hud-dialog-overlay'))return;const t=this.normalize(e);e.repeat||(this.keys.has(t)||this.pressedQueue.push(t),this.keys.add(t),(t==="space"||t==="tab")&&e.preventDefault())}),this.on(window,"keyup",e=>{this.keys.delete(this.normalize(e))}),this.on(window,"blur",()=>{this.keys.clear()}),this.on(document,"mousemove",e=>{this.locked&&(this.pointer.deltaX+=e.movementX||0,this.pointer.deltaY+=e.movementY||0),this.pointer.clientX=e.clientX,this.pointer.clientY=e.clientY;const t=this.element.getBoundingClientRect();this.pointer.x=(e.clientX-t.left)/t.width*2-1,this.pointer.y=-((e.clientY-t.top)/t.height)*2+1}),this.on(this.element,"mousedown",e=>{e.button===0&&(this.pointer.down=!0)}),this.on(window,"mouseup",e=>{if(e.button===0){if(this.pointer.down){this.pointer.clicked=!0;for(const t of this.onClickHandlers)t()}this.pointer.down=!1}}),this.on(window,"wheel",e=>{this.pointer.wheel+=e.deltaY},{passive:!0}),this.on(document,"pointerlockchange",()=>{this.locked=document.pointerLockElement===this.element,!this.locked&&this.mode==="world"&&this.onLockLost?.()})}normalize(e){return Yc[e.key]?Yc[e.key]:e.key==="Shift"?"shift":e.key==="Control"?"control":e.key==="Escape"?"escape":e.key==="Tab"?"tab":e.key.length===1?e.key.toLowerCase():e.key}onLockLost=null;onNextClick(e){return this.onClickHandlers.push(e),()=>{const t=this.onClickHandlers.indexOf(e);t>=0&&this.onClickHandlers.splice(t,1)}}requestLock(){if(this.locked)return;const e=this.element.requestPointerLock?.bind(this.element);if(e){const t=e();t&&typeof t.catch=="function"&&t.catch(()=>{})}}releaseLock(){document.pointerLockElement===this.element&&document.exitPointerLock()}isDown(e){return this.keys.has(e)}wasPressed(e){const t=this.pressedQueue.indexOf(e);return t<0?!1:(this.pressedQueue.splice(t,1),!0)}peekPressed(e){return this.pressedQueue.includes(e)}endFrame(){this.pointer.clicked=!1,this.pointer.deltaX=0,this.pointer.deltaY=0,this.pointer.wheel=0,this.pressedQueue.length=0,this.pressedThisFrame.clear()}dispose(){for(const e of this.listeners)e();this.listeners.length=0,this.onClickHandlers.length=0}}const qc=4.6,mv=7.4,gv=2,vv=46,xv=9,_v=12,yv=26,jc=8.4,Mv=3.4;class bv{constructor(e){this.ladders=e}position=new w(0,0,0);velocity=new w;yaw=0;pitch=0;grounded=!1;crouching=!1;sprinting=!1;inLadder=!1;bobPhase=0;stepTimer=0;focusBlend=0;eyeOffset=new w;get height(){return this.crouching?Z1:K1}get eyeHeight(){return this.crouching?$1:J1}spawn(e,t){this.position.copy(e),this.velocity.set(0,0,0),this.yaw=t,this.pitch=0,this.grounded=!1,this.focusBlend=0}eyePosition(e=new w){const t=Math.sin(this.bobPhase*2)*.028*Math.min(1,this.speedRatio*2);return e.set(this.position.x,this.position.y+this.eyeHeight+t,this.position.z)}get speedRatio(){const e=Math.hypot(this.velocity.x,this.velocity.z);return Math.min(1,e/qc)}ladderAt(e){for(const t of this.ladders)if(e.x>t.min.x&&e.x<t.max.x&&e.z>t.min.z&&e.z<t.max.z&&e.y+this.height>t.min.y&&e.y<t.max.y)return!0;return!1}update(e,t,n,i){const r=i.enabled;if(r&&n.locked){const _=.0022*n.sensitivity;this.yaw-=n.pointer.deltaX*_,this.pitch-=n.pointer.deltaY*_*(n.invertY?-1:1);const v=Math.PI/2-.02;this.pitch=Math.max(-v,Math.min(v,this.pitch))}const o=new w(-Math.sin(this.yaw),0,-Math.cos(this.yaw)),a=new w(Math.cos(this.yaw),0,-Math.sin(this.yaw)),l=new w;r&&((n.isDown("w")||n.isDown("up"))&&l.add(o),(n.isDown("s")||n.isDown("down"))&&l.sub(o),(n.isDown("d")||n.isDown("right"))&&l.add(a),(n.isDown("a")||n.isDown("left"))&&l.sub(a)),l.lengthSq()>0&&l.normalize(),this.crouching=r&&n.isDown("shift");const c=r&&!this.crouching&&n.isDown("control");this.sprinting=c&&l.lengthSq()>0;const h=Math.max(.2,i.speedScale??1),u=(this.crouching?gv:this.sprinting?mv:qc)*h,d=this.grounded?vv:xv,f=l.multiplyScalar(u);if(this.velocity.x=_r(this.velocity.x,f.x,d*e),this.velocity.z=_r(this.velocity.z,f.z,d*e),this.grounded&&l.lengthSq()===0){const _=_v*e;this.velocity.x=_r(this.velocity.x,0,_*Math.abs(this.velocity.x)+_),this.velocity.z=_r(this.velocity.z,0,_*Math.abs(this.velocity.z)+_)}if(this.inLadder=this.ladderAt(this.position),this.inLadder){const _=(r&&(n.isDown("w")||n.isDown("up"))?1:0)-(r&&(n.isDown("s")||n.isDown("down"))?1:0);this.velocity.y=_*Mv,r&&n.isDown("space")&&(this.velocity.y=jc*.6)}else this.velocity.y-=yv*e,this.velocity.y<-60&&(this.velocity.y=-60),r&&this.grounded&&n.isDown("space")&&(this.velocity.y=jc*Math.max(.5,i.jumpScale??1),this.grounded=!1);const g=this.velocity.clone().multiplyScalar(e),x=this.position.clone(),p=ev(t,this.position,this.height,g);this.position.copy(p.position),p.grounded?(this.velocity.y<0&&(this.velocity.y=0),this.grounded=!0):this.grounded=!1,p.hitCeiling&&this.velocity.y>0&&(this.velocity.y=0),p.collidedX&&(this.velocity.x=0),p.collidedZ&&(this.velocity.z=0);const m=Math.hypot(this.position.x-x.x,this.position.z-x.z)/Math.max(e,1e-4);this.grounded&&m>.6?(this.bobPhase+=e*m*1.5,this.stepTimer-=e*m,this.stepTimer<=0&&(this.stepTimer=2.2,i.onStep?.(this.sprinting))):this.bobPhase+=e*.6}}function _r(s,e,t){return s<e?Math.min(s+t,e):s>e?Math.max(s-t,e):s}const wv=[{id:"bridge",label:"01 / 星穹舰桥",description:"灵能护盾穹顶 · 指挥与航行",bounds:[-24,24,-42,0]},{id:"corridor",label:"中轴光廊",description:"前往机械铸造厂",bounds:[-5,5,0,14]},{id:"war-forge",label:"02 / 战争机械装配车间",description:"重型四足机体 · 铸造与武备",bounds:[-32,-5.5,14,58]},{id:"robot-forge",label:"03 / 机器人装配车间",description:"灵能核心 · 机器人与神经矩阵",bounds:[5.5,32,14,58]},{id:"foundry-axis",label:"铸造厂中轴",description:"侧门通向独立车间 · 主路通向太阳核心",bounds:[-5.5,5.5,14,58]},{id:"rear-corridor",label:"恒星光廊",description:"连续米制通道 · 核心舱入口",bounds:[-6,6,58,78]},{id:"reactor",label:"04 / 太阳核心室",description:"太阳核心约束舱 · 星舰供能中枢",bounds:[-18,18,78,118]},{id:"archive-link",label:"记忆连廊",description:"太阳核心与资料室的实体连接",bounds:[18,22,82,90]},{id:"archive",label:"05 / 记忆资料室",description:"水晶档案 · 舰载配置与航行日志",bounds:[22,54,74,106]}],Sv=[{id:"bridge-main",room:"bridge",offset:[0,4],yaw:0,label:"星图仪",hint:"选择航点 / 启动灵能跃迁",kind:"prop",target:"navigation"},{id:"bridge-nav",room:"bridge",offset:[0,-11],yaw:0,label:"指挥核心",hint:"舰船总览与实时指标",kind:"terminal",target:"dashboard"},{id:"bridge-config",room:"archive",offset:[-8,10],yaw:Math.PI,label:"舰载系统",hint:"配置与权限",kind:"terminal",target:"config"},{id:"bridge-logs",room:"archive",offset:[8,10],yaw:Math.PI,label:"记忆水晶",hint:"航行日志",kind:"terminal",target:"logs"},{id:"eng-reactor",room:"reactor",offset:[-12,0],yaw:Math.PI/2,label:"太阳核心终端",hint:"系统状态与资源",kind:"terminal",target:"system"},{id:"eng-power",room:"reactor",offset:[12,0],yaw:-Math.PI/2,label:"能量调谐器",hint:"模型用量与开销",kind:"terminal",target:"usage"},{id:"eng-repair",room:"war-forge",offset:[9.75,13],yaw:Math.PI/2,label:"损管演练",hint:"机械回路抢修",kind:"minigame",target:"repair"},{id:"robot-comms",room:"robot-forge",offset:[-9.75,-14],yaw:-Math.PI/2,label:"机器人中枢",hint:"机器人与会话状态",kind:"terminal",target:"bots"},{id:"robot-modules",room:"robot-forge",offset:[-9.75,0],yaw:-Math.PI/2,label:"装配矩阵",hint:"插件模块装载与启停",kind:"terminal",target:"plugins"},{id:"robot-matrix",room:"robot-forge",offset:[-9.75,13],yaw:-Math.PI/2,label:"神经水晶",hint:"提示词与 Agent 分析",kind:"terminal",target:"analysis"},{id:"bridge-turret",room:"bridge",offset:[17,14],yaw:0,label:"武备演练",hint:"舱外炮塔",kind:"minigame",target:"turret"},{id:"bridge-scores",room:"bridge",offset:[-17,14],yaw:0,label:"远征战绩",hint:"演练排行榜",kind:"terminal",target:"scores"}],Kc=new WeakMap;function Os(s,e={}){const t=new ot(e.scale??1,e.roughnessVariation??.14,e.colourVariation??.07,e.relief??8e-5),n=Kc.get(s);if(n)return n.copy(t),s;Kc.set(s,t);const i=s.onBeforeCompile,r=s.customProgramCacheKey.bind(s)();return s.onBeforeCompile=(o,a)=>{i.call(s,o,a);const l=!!o.uniforms.arkAlloy;o.uniforms.arkAlloy={value:t},!l&&(o.vertexShader=o.vertexShader.replace("#include <common>",`#include <common>
varying vec3 vArkAlloyPosition;`),o.vertexShader=o.vertexShader.replace("#include <begin_vertex>",`#include <begin_vertex>
vArkAlloyPosition = position;`),o.fragmentShader=o.fragmentShader.replace("#include <common>",String.raw`      #include <common>
      varying vec3 vArkAlloyPosition;
      uniform vec4 arkAlloy;
      float arkHash(vec3 p) {
        p = fract(p * 0.1031);
        p += dot(p, p.yzx + 33.33);
        return fract((p.x + p.y) * p.z);
      }
      float arkNoise(vec3 p) {
        vec3 i = floor(p), f = fract(p);
        f = f * f * (3.0 - 2.0 * f);
        return mix(mix(mix(arkHash(i), arkHash(i + vec3(1,0,0)), f.x),
          mix(arkHash(i + vec3(0,1,0)), arkHash(i + vec3(1,1,0)), f.x), f.y),
          mix(mix(arkHash(i + vec3(0,0,1)), arkHash(i + vec3(1,0,1)), f.x),
          mix(arkHash(i + vec3(0,1,1)), arkHash(i + vec3(1,1,1)), f.x), f.y), f.z);
      }
    `),o.fragmentShader=o.fragmentShader.replace("#include <color_fragment>",String.raw`      #include <color_fragment>
      vec3 arkP = vArkAlloyPosition * arkAlloy.x;
      float arkFootprint = max(length(dFdx(arkP)), length(dFdy(arkP)));
      float arkMacroVisibility = 1.0 - smoothstep(0.5, 2.5, arkFootprint);
      float arkMacro = (arkNoise(arkP * 0.73) - 0.5) * arkMacroVisibility;
      float arkGrainVisibility = 1.0 - smoothstep(0.008, 0.06, arkFootprint);
      float arkGrain = (arkNoise(arkP * vec3(34.0, 190.0, 34.0)) - 0.5) * arkGrainVisibility;
      float arkPhase = dot(arkP, vec3(0.78, 0.19, 0.58)) * 870.0;
      float arkBrush = sin(arkPhase) * (1.0 - smoothstep(0.4, 2.0, fwidth(arkPhase)));
      diffuseColor.rgb *= 1.0 + arkAlloy.z * (arkMacro * 1.7 + arkGrain * 0.3);
      float arkRelief = (arkGrain * 0.6 + arkBrush * 0.08) * arkAlloy.w;
    `),o.fragmentShader=o.fragmentShader.replace("#include <roughnessmap_fragment>",String.raw`      #include <roughnessmap_fragment>
      roughnessFactor = clamp(roughnessFactor + arkAlloy.y *
        (arkMacro * 1.5 + arkGrain * 0.65 + arkBrush * 0.08), 0.16, 0.94);
    `),o.fragmentShader=o.fragmentShader.replace("#include <normal_fragment_maps>",String.raw`      #include <normal_fragment_maps>
      // Screen-space surface gradient, no UV tangent frame and no world-space noise.
      vec3 arkDx = dFdx(-vViewPosition), arkDy = dFdy(-vViewPosition);
      vec3 arkR1 = cross(arkDy, normal), arkR2 = cross(normal, arkDx);
      float arkDet = dot(arkDx, arkR1);
      vec3 arkGradient = sign(arkDet) * (dFdx(arkRelief) * arkR1 + dFdy(arkRelief) * arkR2);
      if (abs(arkDet) > 0.0000001) normal = normalize(abs(arkDet) * normal - arkGradient);
    `))},s.customProgramCacheKey=()=>r+"|ark-alloy-v1",s.dithering=!0,s.needsUpdate=!0,s}function Tv(s=Rr){const e=(r,o,a,l,c={})=>{const h=new Ke({color:r,roughness:o,metalness:a,envMapIntensity:l});return Os(h,c)},t=new Ke({color:new Ne(s.energy).multiplyScalar(.22),emissive:s.energy,emissiveIntensity:.9,metalness:.48,roughness:.3,envMapIntensity:.45});t.name="psionic-inlay-not-white";const n=new $h({color:s.glass,roughness:.15,metalness:.08,transparent:!0,opacity:.085,side:Dt,depthWrite:!1,ior:1.46,specularIntensity:.5,envMapIntensity:.65}),i=new Ge({color:new Ne(s.energyCore).lerp(new Ne(s.energy),.68).multiplyScalar(1.08),toneMapped:!0});return{hull:e(s.armour,.43,.74,.64,{roughnessVariation:.055,colourVariation:.025,relief:0}),wall:e(s.structure,.46,.5,.48,{roughnessVariation:.04,relief:0}),wallAccent:e(s.armourEdge,.34,.8,.68,{roughnessVariation:.025,colourVariation:.012,relief:0}),floor:e(s.deck,.49,.46,.35,{scale:1.8,roughnessVariation:.04,colourVariation:.012,relief:0}),ceiling:e(s.recess,.56,.4,.4,{roughnessVariation:.025,relief:0}),prop:e(s.bronze,.47,.57,.48,{roughnessVariation:.045,colourVariation:.025,relief:0}),trim:t,glass:n,emissive:i,screen:new Ge({color:397595,toneMapped:!0})}}function Vr(s,e="",t={}){const n=t.width??512,i=t.height??160,r=t.accent||"#4fd8ff",o=document.createElement("canvas");o.width=n,o.height=i;const a=o.getContext("2d");a.clearRect(0,0,n,i),a.strokeStyle=r,a.lineWidth=1.5,a.beginPath(),a.moveTo(n*.04,i*.57),a.lineTo(n*.16,i*.57),a.moveTo(n*.84,i*.57),a.lineTo(n*.96,i*.57),a.stroke(),a.textAlign="center",a.textBaseline="middle",a.fillStyle="#cbd7df",a.font="500 "+Math.round(i*.34)+'px "Microsoft YaHei", sans-serif',a.fillText(s,n/2,e?i*.39:i*.52,n*.76),e&&(a.fillStyle="#668bb1",a.font=Math.round(i*.125)+'px "Segoe UI", sans-serif',a.fillText(e,n/2,i*.76,n*.8));const l=new ss(o);return l.anisotropy=4,l.colorSpace=Ft,l}function cs(s,e=!1){const t=s[0].index!==null,n=new Set(Object.keys(s[0].attributes)),i=new Set(Object.keys(s[0].morphAttributes)),r={},o={},a=s[0].morphTargetsRelative,l=new je;let c=0;for(let h=0;h<s.length;++h){const u=s[h];let d=0;if(t!==(u.index!==null))return console.error("THREE.BufferGeometryUtils: .mergeGeometries() failed with geometry at index "+h+". All geometries must have compatible attributes; make sure index attribute exists among all geometries, or in none of them."),null;for(const f in u.attributes){if(!n.has(f))return console.error("THREE.BufferGeometryUtils: .mergeGeometries() failed with geometry at index "+h+'. All geometries must have compatible attributes; make sure "'+f+'" attribute exists among all geometries, or in none of them.'),null;r[f]===void 0&&(r[f]=[]),r[f].push(u.attributes[f]),d++}if(d!==n.size)return console.error("THREE.BufferGeometryUtils: .mergeGeometries() failed with geometry at index "+h+". Make sure all geometries have the same number of attributes."),null;if(a!==u.morphTargetsRelative)return console.error("THREE.BufferGeometryUtils: .mergeGeometries() failed with geometry at index "+h+". .morphTargetsRelative must be consistent throughout all geometries."),null;for(const f in u.morphAttributes){if(!i.has(f))return console.error("THREE.BufferGeometryUtils: .mergeGeometries() failed with geometry at index "+h+".  .morphAttributes must be consistent throughout all geometries."),null;o[f]===void 0&&(o[f]=[]),o[f].push(u.morphAttributes[f])}if(e){let f;if(t)f=u.index.count;else if(u.attributes.position!==void 0)f=u.attributes.position.count;else return console.error("THREE.BufferGeometryUtils: .mergeGeometries() failed with geometry at index "+h+". The geometry must have either an index or a position attribute"),null;l.addGroup(c,f,h),c+=f}}if(t){let h=0;const u=[];for(let d=0;d<s.length;++d){const f=s[d].index;for(let g=0;g<f.count;++g)u.push(f.getX(g)+h);h+=s[d].attributes.position.count}l.setIndex(u)}for(const h in r){const u=Zc(r[h]);if(!u)return console.error("THREE.BufferGeometryUtils: .mergeGeometries() failed while trying to merge the "+h+" attribute."),null;l.setAttribute(h,u)}for(const h in o){const u=o[h][0].length;if(u===0)break;l.morphAttributes=l.morphAttributes||{},l.morphAttributes[h]=[];for(let d=0;d<u;++d){const f=[];for(let x=0;x<o[h].length;++x)f.push(o[h][x][d]);const g=Zc(f);if(!g)return console.error("THREE.BufferGeometryUtils: .mergeGeometries() failed while trying to merge the "+h+" morphAttribute."),null;l.morphAttributes[h].push(g)}}return l}function Zc(s){let e,t,n,i=-1,r=0;for(let c=0;c<s.length;++c){const h=s[c];if(e===void 0&&(e=h.array.constructor),e!==h.array.constructor)return console.error("THREE.BufferGeometryUtils: .mergeAttributes() failed. BufferAttribute.array must be of consistent array types across matching attributes."),null;if(t===void 0&&(t=h.itemSize),t!==h.itemSize)return console.error("THREE.BufferGeometryUtils: .mergeAttributes() failed. BufferAttribute.itemSize must be consistent across matching attributes."),null;if(n===void 0&&(n=h.normalized),n!==h.normalized)return console.error("THREE.BufferGeometryUtils: .mergeAttributes() failed. BufferAttribute.normalized must be consistent across matching attributes."),null;if(i===-1&&(i=h.gpuType),i!==h.gpuType)return console.error("THREE.BufferGeometryUtils: .mergeAttributes() failed. BufferAttribute.gpuType must be consistent across matching attributes."),null;r+=h.count*t}const o=new e(r),a=new kt(o,t,n);let l=0;for(let c=0;c<s.length;++c){const h=s[c];if(h.isInterleavedBufferAttribute){const u=l/t;for(let d=0,f=h.count;d<f;d++)for(let g=0;g<t;g++){const x=h.getComponent(d,g);a.setComponent(d+u,g,x)}}else o.set(h.array,l);l+=h.count*t}return i!==void 0&&(a.gpuType=i),a}function ka(s,e=Math.PI/3){const t=Math.cos(e),n=(1+1e-10)*100,i=[new w,new w,new w],r=new w,o=new w,a=new w,l=new w;function c(x){const p=~~(x.x*n),m=~~(x.y*n),_=~~(x.z*n);return`${p},${m},${_}`}const h=s.index?s.toNonIndexed():s,u=h.attributes.position,d={};for(let x=0,p=u.count/3;x<p;x++){const m=3*x,_=i[0].fromBufferAttribute(u,m+0),v=i[1].fromBufferAttribute(u,m+1),M=i[2].fromBufferAttribute(u,m+2);r.subVectors(M,v),o.subVectors(_,v);const S=new w().crossVectors(r,o).normalize();for(let E=0;E<3;E++){const C=i[E],z=c(C);z in d||(d[z]=[]),d[z].push(S)}}const f=new Float32Array(u.count*3),g=new kt(f,3,!1);for(let x=0,p=u.count/3;x<p;x++){const m=3*x,_=i[0].fromBufferAttribute(u,m+0),v=i[1].fromBufferAttribute(u,m+1),M=i[2].fromBufferAttribute(u,m+2);r.subVectors(M,v),o.subVectors(_,v),a.crossVectors(r,o).normalize();for(let S=0;S<3;S++){const E=i[S],C=c(E),z=d[C];l.set(0,0,0);for(let T=0,y=z.length;T<y;T++){const b=z[T];a.dot(b)>t&&l.add(b)}l.normalize(),g.setXYZ(m+S,l.x,l.y,l.z)}}return h.setAttribute("normal",g),h}class En{constructor(e){this.root=e}batches=new Map;add(e,t){if(e.index){const i=e.toNonIndexed();e.dispose(),e=i}e.deleteAttribute("uv");const n=this.batches.get(t)??[];n.push(e),this.batches.set(t,n)}box(e,t,n){this.add(new lt(...e).translate(...t),n)}curve(e,t,n,i=36){this.add(new Si(new hn(e.map(r=>new w(...r))),i,t,6,!1),n)}plate(e,t,n,i,r=!1){const o=new xt(e,{depth:t,bevelEnabled:!0,bevelThickness:Math.min(.12,t*.25),bevelSize:.12,bevelSegments:3,steps:1,curveSegments:24});if(r){o.scale(-1,1,1);const a=o.index;if(a)for(let l=0;l<a.count;l+=3){const c=a.getX(l+1);a.setX(l+1,a.getX(l+2)),a.setX(l+2,c)}else{const l=o.attributes.position,c=o.attributes.normal,h=o.attributes.uv;for(let u=0;u<l.count;u+=3)for(const d of[l,c,h])if(d)for(let f=0;f<d.itemSize;f++){const g=d.array,x=(u+1)*d.itemSize+f,p=(u+2)*d.itemSize+f,m=g[x];g[x]=g[p],g[p]=m}}}o.translate(...n),this.add(o,i)}ring(e,t,n,i,r=!1){const o=new at(e,t,6,80);r||o.rotateX(Math.PI/2),o.translate(...n),this.add(o,i)}blade(e,t){const n=[],i=[];for(const[a,l,c,h,u]of e)for(let d=0;d<24;d++){const f=d/24*Math.PI*2;n.push(a+Math.cos(f)*h,l+Math.sin(f)*u,c)}for(let a=0;a<e.length-1;a++)for(let l=0;l<24;l++){const c=a*24+l,h=a*24+(l+1)%24,u=c+24,d=h+24;i.push(c,h,u,h,d,u)}for(let a=1;a<23;a++){i.push(0,a+1,a);const l=(e.length-1)*24;i.push(l,l+a,l+a+1)}const o=new je;o.setAttribute("position",new Ae(n,3)),o.setIndex(i),o.computeVertexNormals(),this.add(o,t)}finish(){for(const[e,t]of this.batches){const n=cs(t,!1);for(const i of t)i.dispose();n&&this.root.add(new ve(n,e))}this.batches.clear()}}const yr=[[1,0],[.98,.2],[.86,.68],[.67,.89],[-.43,1],[-.79,.77],[-.97,.2],[-1,0],[-.89,-.72],[-.5,-1],[.58,-.92],[.91,-.6],[1,0]];function Ev(s,e,t,n){const i=a=>{const l=_t.clamp(a,0,1)*(e.length-1),c=Math.min(e.length-2,Math.floor(l)),h=l-c;return e[c].map((u,d)=>{if(d===2)return _t.lerp(u,e[c+1][d],h);const f=e[Math.max(0,c-1)][d],g=e[c+1][d],x=e[Math.min(e.length-1,c+2)][d],p=(2*h*h*h-3*h*h+1)*u+(h*h*h-2*h*h+h)*(g-f)*.35+(-2*h*h*h+3*h*h)*g+(h*h*h-h*h)*(x-u)*.35;return d>=3&&d<=5?Math.max(.08,p):p})},r=(a,l,c=0)=>{const[h,u,d,f,g,x,p]=i(a),m=_t.clamp(l,0,1)*12,_=Math.min(11,Math.floor(m)),v=m-_,M=_t.lerp(yr[_][0],yr[_+1][0],v),S=_t.lerp(yr[_][1],yr[_+1][1],v);return new w(t*(h+M*(f+c)),u+S*((S>=0?g:x)+c)+M*f*p,d)},o=(a,l,c,h,u,d,f)=>{const g=D=>D.sort((L,N)=>L-N).filter((L,N,B)=>N===0||L-B[N-1]>1e-7),x=(e.length-1)*7,p=g([a,l,...Array.from({length:x+1},(D,L)=>L/x).filter(D=>D>a&&D<l)]);p.length<4&&p.splice(1,0,_t.lerp(a,l,.3333333333333333),_t.lerp(a,l,.6666666666666666));const m=g([c,h,...Array.from({length:37},(D,L)=>L/36).filter(D=>D>c&&D<h)]);m.length<4&&m.splice(1,0,_t.lerp(c,h,.3333333333333333),_t.lerp(c,h,.6666666666666666)),p.sort((D,L)=>D-L),m.sort((D,L)=>D-L);const _=p.length-1,v=m.length-1,M=[],S=[],E=D=>(M.push(D.x,D.y,D.z),M.length/3-1),C=(D,L,N)=>{t<0?S.push(D,N,L):S.push(D,L,N)};for(let D=0;D<=_;D++)for(let L=0;L<=v;L++){const N=f?1:Math.min(1,D/1.15,(_-D)/1.15,L/1.1,(v-L)/1.1);E(r(p[D],m[L],u*(.25+.75*N)))}for(let D=0;D<_;D++)for(let L=0;L<v;L++){const N=D*(v+1)+L;C(N,N+1,N+v+1),C(N+1,N+v+2,N+v+1)}if(f)for(const D of[0,_]){const[L,N,B]=i(D===0?a:l),k=E(new w(t*L,N,B));for(let q=0;q<v;q++){const U=D*(v+1)+q;D===0?C(k,U+1,U):C(k,U,U+1)}}else{const D=[];for(let L=0;L<=v;L++)D.push(L);for(let L=1;L<=_;L++)D.push(L*(v+1)+v);for(let L=v-1;L>=0;L--)D.push(_*(v+1)+L);for(let L=_-1;L>0;L--)D.push(L*(v+1));for(let L=0;L<D.length;L++){const N=D[L],B=D[(L+1)%D.length],k=V=>r(p[Math.floor(V/(v+1))],m[V%(v+1)],-.12),q=E(k(N)),U=E(k(B));C(N,q,B),C(B,q,U)}}const z=new je;z.setAttribute("position",new Ae(M,3)),z.setIndex(S),z.computeVertexNormals();const T=z.toNonIndexed(),y=T.getAttribute("normal"),b=_*v*6;for(let D=0;D<b;D+=3){const L=[S[D],S[D+1],S[D+2]].map(k=>k%(v+1)),N=(m[L[0]]+m[L[1]]+m[L[2]])/3,B=Math.min(11,Math.floor(N*12));for(let k=0;k<3;k++){const q=S[D+k],U=Math.floor(q/(v+1)),V=q%(v+1);if(!f&&(U<2||U>_-2||V<2||V>v-2))continue;const P=p[U],O=m[V],H=r(Math.min(1,P+.001),O,u).sub(r(Math.max(0,P-.001),O,u)),W=r(P,(B+1)/12,u).sub(r(P,B/12,u)).cross(H).multiplyScalar(t).normalize();y.setXYZ(D+k,W.x,W.y,W.z)}}z.dispose(),s.add(T,d)};return o(0,1,0,1,0,n,!0),{point:(a,l,c=0)=>r(a,l,c).toArray(),panel:(a,l,c,h,u,d)=>o(a,l,c,h,u,d,!1)}}function Av(s,e,t,n,i,r){const o=e.map(_=>new w(..._)),a=o.reduce((_,v)=>_.add(v),new w).multiplyScalar(1/o.length),l=o[1].clone().sub(o[0]).cross(o[2].clone().sub(o[0])).normalize(),c=o.map(_=>_.clone().lerp(a,.14).addScaledVector(l,-t*.22)),h=o.map(_=>_.clone().addScaledVector(l,-t)),u=o.map(_=>_.clone().lerp(a,.14).addScaledVector(l,-t*.78)),d=(_,v)=>{const M=new je;M.setAttribute("position",new Ae(_.flatMap(S=>S.toArray()),3)),M.computeVertexNormals(),s.add(M,v)},f=[],g=[],x=[],p=a.clone().addScaledVector(l,-t*.22),m=a.clone().addScaledVector(l,-t*.78);for(let _=0;_<o.length;_++){const v=(_+1)%o.length;f.push(o[_],o[v],c[v],o[_],c[v],c[_]),f.push(o[v],o[_],h[_],o[v],h[_],h[v]),g.push(c[_],c[v],p),f.push(h[v],h[_],u[_],h[v],u[_],u[v]),x.push(u[v],u[_],m)}d(f,n),d(g,i),d(x,r)}function Cv(s){const e=new qe;e.name="ark-exterior-normalized";const t=new En(e),n=s.hull.clone(),i=s.wallAccent.clone(),r=s.prop;n.color.setHex(10325849),n.metalness=.65,n.roughness=.48,n.envMapIntensity=.85,i.color.setHex(12495992),i.roughness=.36,i.envMapIntensity=.85;const o=s.ceiling,a=s.trim,l=s.wall.clone();l.color.setHex(1587007),l.metalness=.58,l.roughness=.38,l.name="ark-dark-teal-structure";const c=(U,V,P,O)=>new Fe().makeBasis(new w(...V),new w(...P),new w(...O)).setPosition(...U),h=(U,V,P=0,O=0)=>c([0,V,0],[U,P,0],[0,O,1],[0,-1,0]),u=(U,V,P,O=0)=>new w(V,P,O).applyMatrix4(U).toArray(),d=(U,V=[])=>{const P=new De(U.map(O=>new Q(...O)));P.closePath();for(const O of V){const H=new vi(O.map(Z=>new Q(...Z)));H.closePath(),P.holes.push(H)}return P},f=(U,V,P)=>{if(U.applyMatrix4(V),V.determinant()<0)if(U.index){const O=U.index;for(let H=0;H<O.count;H+=3){const Z=O.getX(H+1);O.setX(H+1,O.getX(H+2)),O.setX(H+2,Z)}}else for(const O of Object.values(U.attributes)){const H=O.array,Z=O.itemSize;for(let W=0;W<O.count;W+=3)for(let $=0;$<Z;$++){const le=(W+1)*Z+$,he=(W+2)*Z+$,Ce=H[le];H[le]=H[he],H[he]=Ce}}t.add(U,P)},g=(U,V,P,O,H=[],Z=.45)=>{const W=new xt(U instanceof De?U:d(U,H),{depth:P,steps:1,bevelEnabled:Z>0,bevelSize:Z,bevelThickness:Z*.6,bevelSegments:2,curveSegments:32});f(W,V,O)},x=(U,V,P=.32,O=o,H=-.12)=>{for(let Z=1;Z<V.length;Z++){const W=new w(...u(U,...V[Z-1],H)),$=new w(...u(U,...V[Z],H)),le=$.clone().sub(W),he=new lt(P,P,le.length()+P*.25);he.applyQuaternion(new Pt().setFromUnitVectors(new w(0,0,1),le.normalize())),he.translate(...W.add($).multiplyScalar(.5).toArray()),t.add(he,O)}},p=(U,V,P=r,O=.65)=>x(U,[...V,V[0]],O,P,-.28),m=(U,V,P,O,H)=>{const Z=new w(...U),W=new w(...V),$=W.clone().sub(Z),le=new lt(P,O,$.length());le.applyQuaternion(new Pt().setFromUnitVectors(new w(0,0,1),$.normalize())),le.translate(...Z.add(W).multiplyScalar(.5).toArray()),t.add(le,H)},_=(U,V,P,O,H=1)=>{f(new et(O*1.21,O*1.27,1.3,32).rotateX(Math.PI/2).translate(V,P,.2),U,o),f(new at(O*1.12,.65,6,36).scale(1,H,1).translate(V,P,-.7),U,i),f(new ft(O,24,12).scale(1,H,.25).translate(V,P,-.6),U,a);for(const Z of[-1,1])x(U,[[V+Z*O*.5,P-O*.7*H],[V+Z*O*.8,P],[V+Z*O*.5,P+O*.7*H]],.35,r,-O*.23-.8)},v=(U,V=1,P=[0,.28,.66,1])=>{const O=Ev(t,U,V,l);for(let H=1;H<P.length;H++){const Z=P[H-1]+.005,W=P[H]-.006;O.panel(Z,W,.025,.205,1.4,n);const $=H===1?.006:Math.min(.97,P[H-1]+.075),le=H===P.length-1?.994:Math.min(.98,P[H]+.064);O.panel($,le,.285,.455,1.65,n),O.panel(Math.max(.005,Z-.035),Math.min(.995,W+.015),.69,.91,.95,r)}return O.panel(.012,.987,.005,.024,.9,i),O},M=(U,V,P=.5,O=.73)=>{for(const H of V){U.panel(H-.007,H+.007,P,O,1,r);const Z=U.point(H,(P+O)*.5,1.25);t.add(new lt(.8,.9,1.6).translate(...Z),a)}},S=new w;v([[0,-1,-500,.1,.2,.2,0],[0,-4,-456,6,4,4,0],[0,-10,-394,15,7,11,0],[0,-12,-330,25,12,18,0],[0,-13,-280,27,12,17,0],[0,-16,-238,17,8,12,0]],1,[0,.38,.7,1]).panel(.22,.51,.21,.28,1.1,o);for(const U of[-1,1]){const V=v([[2,0,-482,.15,.3,.4,0],[12,0,-421,5,5,6,-.2],[25,1,-352,11,10,16,-.3],[31,3,-292,15,18,20,-.4],[25,0,-238,9,15,14,-.3]],U,[0,.34,.73,1]);if(V.panel(.28,.61,.12,.24,1.9,o),V.panel(.33,.58,.145,.205,2.1,a),M(V,[.64,.68,.72,.77,.82],.51,.76),U===1){S.fromArray(V.point((2+32/60)/4,4/12,1.65)),S.y+=.65;const O=S.x,H=S.z,Z=1.38,W=1.7473;g([[O-Z,H-W],[O+Z,H-W],[O+Z,H+W],[O-Z,H+W]],h(1,S.y),2,n,[],0)}v([[35,-14,-271,5,5,7,0],[29,12,-248,8,9,8,-.2],[12,28,-232,7,5,7,-.3],[4,30,-220,2,2,2,0]],U,[0,.48,1]).panel(.26,.61,.17,.3,2.1,r)}_(h(1,4),0,-390,7,2.4);for(const U of[-1,1]){const V=v([[27,-15,-259,9,12,12,0],[39,-20,-215,15,15,17,-.15],[54,-31,-140,19,13,18,-.25],[68,-33,-50,24,15,19,-.18],[79,-32,47,27,16,20,-.28],[80,-30,128,27,18,20,-.38],[68,-29,188,20,17,20,-.25]],U,[0,.21,.51,.73,1]);V.panel(.24,.52,.46,.57,.55,o),V.panel(.56,.74,.46,.57,.55,o),M(V,[.27,.31,.36,.43,.48,.58,.62,.69,.81,.84,.87],.45,.67);const P=v([[53,-18,-102,1,2,3,0],[68,-19,-25,18,13,12,-.3],[81,-19,62,24,14,15,-.4],[75,-17,126,24,15,15,-.3],[66,-20,174,10,10,10,0]],U,[0,.46,1]);P.panel(.22,.63,.26,.39,2.5,r),P.panel(.28,.57,.28,.35,2.7,o);const O=v([[8,21,-109,.15,.2,.2,0],[29,29,-61,11,9,11,-.35],[45,34,4,18,14,18,-.45],[51,34,76,21,18,22,-.5],[41,30,151,22,19,22,-.38],[18,24,229,15,13,16,-.2]],U,[0,.4,.68,1]);O.panel(.35,.65,.26,.4,2.9,n),O.panel(.44,.61,.11,.21,1.95,o),M(O,[.69,.73,.77,.82,.87],.53,.81);const H=c([U*46,0,0],[0,1,0],[0,0,1],[-U,0,0]),Z=[[-24,125],[-12,65],[26,78],[37,125],[24,181],[-7,171]],W=[[0,104],[18,103],[20,126],[4,147],[-5,142]];g(Z,H,7,l,[W],1.2),p(H,W,r,1.5),g([[27,121],[19,165],[4,168],[9,141]],H.clone().multiply(new Fe().makeTranslation(0,0,-1.2)),3,n,[],.7);for(const $ of[87,96,156,165])m([U*47,-6,$],[U*47,18,$+7],1.8,2.2,r)}for(const U of[-1,1]){const V=v([[68,-29,114,19,17,20,-.2],[83,-25,180,25,18,23,-.25],[91,-25,259,24,19,23,-.22],[96,-23,330,20,17,21,-.2],[92,-20,398,15,14,17,-.16],[98,-13,461,5,6,6,0],[105,-10,489,.1,.1,.1,0]],U,[0,.26,.57,.8,1]);V.panel(.15,.36,.27,.4,2.9,n),V.panel(.41,.67,.1,.2,1.9,o),M(V,[.18,.22,.26,.48,.52,.57,.62,.68,.73],.52,.79);const P=v([[14,38,238,18,18,23,-.4],[42,32,276,23,19,26,-.5],[66,5,319,25,19,25,-.45],[85,-15,361,21,21,21,-.3],[92,-20,413,12,13,15,0]],U,[0,.52,1]);P.panel(.12,.77,.13,.28,2.3,n),P.panel(.23,.63,.33,.39,1.9,o),M(P,[.18,.23,.28,.69,.74,.8],.54,.79),v([[17,-30,177,8,9,11,0],[40,-43,227,11,11,11,.2],[64,-38,283,13,10,12,.3],[85,-24,339,12,12,13,.2]],U,[0,.37,.74,1]),v([[73,-17,126,10,10,14,0],[61,7,168,16,14,17,-.3],[39,32,219,16,14,19,-.45],[10,35,257,11,10,14,-.3]],U,[0,.55,1]),v([[96,-20,285,8,8,11,0],[107,-22,350,10,8,10,.1],[110,-17,409,5,5,7,.1],[115,-9,438,.1,.2,.2,0]],U,[0,.67,1])}const C=v([[0,-3,42,17,18,20,0],[0,-1,105,31,29,29,0],[0,0,184,40,36,34,0],[0,0,267,43,39,36,0],[0,0,330,33,34,33,0],[0,0,348,28,30,30,0]],1,[0,.22,.48,.77,1]);C.panel(.16,.84,.055,.13,2.3,o),C.panel(.16,.84,.45,.53,2.3,o),M(C,[.21,.25,.3,.36,.41,.49,.57,.64,.71,.76],.04,.16);const z=v([[0,31,193,14,10,16,0],[0,39,264,32,20,25,0],[0,44,337,43,26,30,0],[0,48,394,34,23,25,0],[0,49,452,17,13,16,0],[0,50,500,.1,.2,.3,0]],1,[0,.29,.63,1]);z.panel(.15,.7,.19,.36,3,n),z.panel(.3,.73,.1,.16,2,o),z.panel(.3,.73,.41,.47,2,o),_(h(1,70),0,337,10.5,2.3);const T=c([0,0,353],[1,0,0],[0,1,0],[0,0,-1]),y=[[-17,-42],[17,-42],[30,-30],[37,-10],[35,17],[23,39],[-23,39],[-35,17],[-37,-10],[-30,-30]],b=d(y),D=[[0,19,13.5],[0,-19,12.5],[-22,0,8],[22,0,8]];for(const[U,V,P]of D){const O=new vi;O.absarc(U,V,P*1.1,0,Math.PI*2,!0),b.holes.push(O)}g(b,T,19,l,[],1),g(y,T,5,r,[y.map(([U,V])=>[U*.84,V*.86])],.7);for(const U of[-1,1]){m([U*30,21,347],[U*79,-8,348],9,8,l),m([U*31,-24,347],[U*64,-31,312],7,7,r);for(const P of[-27,-16,9,20])x(T,[[U*28,P],[U*31,P+5],[U*29,P+10]],1.15,r,-.8),x(T,[[U*31,P+1],[U*32,P+5]],.52,a,-1);const V=c([U*25,0,0],[0,1,0],[0,0,1],[-U,0,0]);g([[-21,268],[19,275],[25,319],[17,338],[-23,332]],V,3,o,[],.65);for(const P of[278,286,297,309,321])x(V,[[-18,P],[-5,P+3],[16,P+2]],1.4,r,-1),x(V,[[-9,P+2],[-3,P+3]],.62,a,-1.8)}for(const[U,V,P]of D){t.add(new et(P*1.32,P*1.1,12,24,1,!0).rotateX(Math.PI/2).translate(U,V,350),r),t.add(new at(P*1.12,2.2,8,32).translate(U,V,357),i),t.add(new rs(P,32).translate(U,V,352),o),t.add(new at(P*.76,1.25,6,32).translate(U,V,353),a),t.add(new rs(P*.65,24).translate(U,V,353.1),a);for(let O=0;O<10;O++){const H=O*Math.PI/5;m([U+Math.cos(H)*P*.8,V+Math.sin(H)*P*.8,353],[U+Math.cos(H)*P*1.13,V+Math.sin(H)*P*1.13,357],1,1,r)}}t.add(new ft(1,40,28).scale(20,20,37).translate(0,0,-22),a);for(let U=0;U<7;U++){const V=U*Math.PI*2/7,P=[];for(let O=0;O<=22;O++){const H=.13+O/22*(Math.PI-.26),Z=Math.sin(H);P.push([Math.cos(V)*20.7*Z,Math.sin(V)*20.7*Z,-22+Math.cos(H)*38])}t.curve(P,.85,U%2?r:i,32)}for(const U of[15,34,58,85,112])t.add(new et(19,20,7,24,1,!0).rotateX(Math.PI/2).translate(0,0,U),r),t.ring(19.4,1.2,[0,0,U+3.6],i,!0);t.add(new et(13.5,17,100,16).rotateX(Math.PI/2).translate(0,-3,66),o);for(const U of[-1,1]){v([[13,-8,108,5,6,7,0],[29,-25,132,7,9,9,.2],[51,-20,153,8,8,8,0]],U,[0,.5,1]);for(const[V,P,O]of[[77,13,92],[90,8,204],[91,11,290],[50,41,118]]){const H=h(U,P,-.2);_(H,V,O,3.1,1.4);for(let Z=0;Z<3;Z++)x(H,[[V-7+Z*2,O-8],[V-5+Z*2,O-2],[V-5+Z*2,O+4]],.85,r,-.2)}}const L=l.clone();L.name="ark-recessed-energy-armour",L.color.setHex(1461092),L.emissive.setHex(737629),L.emissiveIntensity=.4,L.metalness=.42,L.roughness=.32;for(const U of[-1,1]){const V=(P,O,H=l)=>{const Z=P.map(([W,$,le])=>[U*W,$,le]);U<0&&Z.reverse(),Av(t,Z,O,n,H,H===L?L:o)};V([[19,-26,-228],[32,-9,-194],[44,-11,-119],[25,-30,-131]],2.5,L),V([[25,-30,-130],[44,-11,-118],[55,-11,-33],[30,-31,-45]],2.8,L),V([[30,-31,-44],[55,-11,-32],[61,-11,60],[35,-27,75]],3,L),V([[27,17,153],[43,29,214],[85,-7,254],[66,-28,177]],8,l),V([[28,-17,174],[65,-35,206],[86,-23,303],[43,-29,274]],7,l),V([[31,49,243],[56,33,224],[70,3,173],[46,8,184]],2.8,L),V([[34,-29,170],[64,-30,209],[77,-23,271],[43,-42,240]],2.8,L),V([[63,-7,-41],[82,2,29],[88,-3,80],[73,-4,57]],2.4,o),V([[15,47,271],[27,55,315],[25,56,358],[13,55,334]],2.4,l),v([[20,42,271,8,7,9,0],[35,48,319,13,9,12,-.15],[41,48,370,11,10,12,-.2],[39,50,428,.15,.3,.3,0]],U,[0,.48,1]),v([[30,33,277,8,8,10,0],[47,37,316,10,9,11,-.2],[58,37,380,.15,.3,.3,0]],U,[0,.58,1]),v([[91,-13,343,9,7,10,0],[103,-12,397,10,7,9,0],[112,-8,463,.2,.3,.3,0]],U,[0,.55,1]),v([[85,-27,321,9,7,9,0],[94,-29,375,11,8,10,0],[98,-25,426,.1,.2,.2,0]],U,[0,.6,1])}t.finish(),e.updateMatrixWorld(!0);const N=new Lt().setFromObject(e),B=N.getSize(new w),k=new w(230/B.x,123/B.y,1e3/B.z),q=new Fe().makeScale(k.x,k.y,k.z);return q.setPosition(-115-N.min.x*k.x,-70-N.min.y*k.y,-500-N.min.z*k.z),e.traverse(U=>{U instanceof ve&&(U.geometry.applyMatrix4(q),U.geometry.computeBoundingBox(),U.geometry.computeBoundingSphere(),U.name="ark-batched-"+(U.material.name||U.material.type),U.castShadow=!0,U.receiveShadow=!0)}),e.userData.mountPoint=S.applyMatrix4(q).toArray(),e.userData.engineExhausts=D.map(([U,V,P])=>({position:new w(U,V,359.2).applyMatrix4(q).toArray(),direction:new w(0,0,1).transformDirection(q).toArray(),radius:P*Math.min(k.x,k.y)})),e.userData.designDimensions={length:1e3,width:230,height:123},e.userData.forwardAxis="-z",e.userData.silhouette="thick chined spear / open reactor nave / vaulted engine crown",e.userData.reference="Spear_of_Adun_Front_LotV + Spear_of_Adun_Rear_LotV (both viewed)",e}const Cs=Object.freeze({length:74400,width:17204,height:9139}),Jc=2e6,Pv=`
#include <common>
#include <logdepthbuf_pars_vertex>
attribute float rimDistance;
varying float vRimDistance;
varying vec2 vUv;
varying vec3 vNormal;
varying vec3 vView;
void main() {
  vUv = uv;
  vRimDistance = rimDistance;
  vec4 view = modelViewMatrix * vec4(position, 1.0);
  vView = -view.xyz;
  vNormal = normalize(normalMatrix * normal);
  gl_Position = projectionMatrix * view;
  #include <logdepthbuf_vertex>
}
`,Rv=`
#include <logdepthbuf_pars_fragment>
uniform float uTime;
uniform vec2 uSpan;
uniform float uStrength;
varying float vRimDistance;
varying vec2 vUv;
varying vec3 vNormal;
varying vec3 vView;
float hexEdge(vec2 p) {
  vec2 repeat = vec2(1.0, 1.7320508);
  vec2 a = mod(p, repeat) - repeat * .5;
  vec2 b = mod(p - repeat * .5, repeat) - repeat * .5;
  vec2 q = dot(a,a) < dot(b,b) ? a : b;
  q = abs(q);
  float d = max(q.x, dot(q, vec2(.5, .8660254)));
  float aa = max(fwidth(d) * 1.2, .010);
  return 1.0 - smoothstep(.010, .010 + aa, abs(d - .5));
}
void main() {
  #include <logdepthbuf_fragment>
  // MSAA can interpolate outside a subpixel triangle at orbital distances.
  // Never exponentiate a negative edge distance: it explodes into a white flare.
  vec2 uv = clamp(vUv, vec2(0.0), vec2(1.0));
  vec2 field = uv * uSpan;
  float edgeDistance = max(0.0, vRimDistance);
  float border = exp(-edgeDistance * 1.7);
  float facing = clamp(abs(dot(normalize(vNormal), normalize(vView))), 0.0, 1.0);
  float fresnel = pow(1.0 - facing, 2.1);
  float ripple = pow(.5 + .5 * sin(field.y * .64 - uTime * .32 + sin(field.x * .21) * 1.4), 26.0);
  float cells = hexEdge(field / 1.25);
  float seams = 1.0 - smoothstep(.018, .055, edgeDistance);
  float alpha = (.13 + fresnel * .19 + border * .19 + cells * .027 + ripple * .025) * uStrength;
  vec3 color = mix(vec3(.015,.13,.37), vec3(.065,.39,.88), clamp(fresnel * .55 + border * .65, 0.0, 1.0));
  color += vec3(.04,.23,.48) * (cells * .25 + ripple * .5 + seams * 1.6);
  gl_FragColor = vec4(color, clamp(alpha, .07, .53));
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}
`;function Dv(s){const e=new qe;e.name="bridge-psionic-shield";const t=34,n=24.5,i=31,r=-2,o=-21,a=.25,l=Math.sqrt(1-((a-r)/n)**2),c=o-i*l,h=112,u=88,d=[],f=[],g=[],x=[],p=[];for(let T=0;T<=u;T++){const y=c+(0-c)*T/u,b=(y-o)/i,D=Math.sqrt(Math.max(0,1-b*b)),L=Math.acos(Math.min(1,(a-r)/(n*D)));for(let N=0;N<=h;N++){const B=-L+2*L*N/h,k=t*D*Math.sin(B),q=r+n*D*Math.cos(B);d.push(k,q,y);const U=new w(k/(t*t),(q-r)/(n*n),(y-o)/(i*i)).normalize();if(f.push(U.x,U.y,U.z),g.push(.5+B/Math.PI,(Math.asin(b)+Math.PI/2)/Math.PI),x.push(Math.max(0,Math.min((L-Math.abs(B))*Math.sqrt(t*n)*D,-y))),T<u&&N<h){const V=T*(h+1)+N;p.push(V,V+1,V+h+1,V+1,V+h+2,V+h+1)}}}const m=new je;m.setAttribute("position",new Ae(d,3)),m.setAttribute("normal",new Ae(f,3)),m.setAttribute("uv",new Ae(g,2)),m.setAttribute("rimDistance",new Ae(x,1)),m.setIndex(p),m.computeBoundingSphere();const _=new gt({name:"continuous-psionic-canopy",vertexShader:Pv,fragmentShader:Rv,uniforms:{uTime:{value:0},uSpan:{value:new Q(93,88)},uStrength:{value:.92}},transparent:!0,depthWrite:!1,side:Dt,blending:Qn}),v=new ve(m,_);v.name="continuous-ellipsoidal-field",v.userData.psionicPane=!0,e.add(v);const M=Math.acos(o/(i*l)),S=[];for(let T=0;T<=160;T++){const y=-M+2*M*T/160;S.push(new w(t*l*Math.sin(y),a,o-i*l*Math.cos(y)))}const E=new Si(new hn(S),200,.055,6,!1),C=new ve(E,s.trim);C.name="curved-field-sill",e.add(C);const z=new Ke({color:2311811,emissive:3579647,emissiveIntensity:1.5,roughness:.3,metalness:.25});for(const T of[-1.9,-1.2,-.55,0,.55,1.2,1.9]){const y=t*l*Math.sin(T),b=o-i*l*Math.cos(T),D=new ve(new et(.3,.4,1.5,12),s.hull);D.position.set(y,-.45,b),e.add(D);const L=new ve(new qt(.16),z);L.scale.y=1.5,L.position.set(y,.5,b),e.add(L)}return e.userData.update=T=>{Number.isFinite(T)&&T>0&&(_.uniforms.uTime.value+=Math.min(T,.1))},e.userData.paneCount=1,e.userData.surface="continuous ellipsoid",e.userData.bounds={frontZ:c,halfWidth:t,roofApex:r+n,rearZ:0},e}function Iv(s,e){const t=new qe;t.name="celestial-sanctum";const n=new En(t),i=s.hull,r=s.wallAccent,o=s.ceiling,a=s.wall,l=(v,M,S,E,C=!1)=>n.plate(v,M,S,E,C),c=(v,M=.025)=>n.curve(v,M,o,36),h=new Ge({color:2723317,transparent:!0,opacity:.7}),u=new Ke({color:1391735,emissive:3772159,emissiveIntensity:2,metalness:.35,roughness:.25});for(let v=0;v<12;v++){const M=v*Math.PI/6+.016,S=(v+1)*Math.PI/6-.016,E=new De;E.absarc(0,0,19.9,M,S,!1),E.absarc(0,0,5.7,S,M,!0),E.closePath();const C=new xt(E,{depth:.012,bevelEnabled:!0,bevelThickness:.002,bevelSize:.04,bevelSegments:2,curveSegments:32});C.rotateX(-Math.PI/2),C.translate(0,.003,-21),n.add(C,v%3===0?s.floor:s.prop);const z=[];for(let T=0;T<=30;T++){const y=M+(S-M)*T/30;z.push([Math.cos(y)*19.3,.024,-21-Math.sin(y)*19.3])}n.curve(z,.006,r,32)}for(const v of[4.8,5,5.65,20.2])n.ring(v,.013,[0,.024,-21],v===5?h:o);n.box([2.6,.01,26],[0,.023,-22],o);for(const v of[-1,1])n.curve([[v*1.25,.033,-40],[v*1.25,.033,-28],[v*1.7,.033,-20],[v*2.4,.033,-10]],.008,r),n.curve([[v*1.12,.036,-37],[v*1.12,.036,-28],[v*1.55,.036,-20]],.006,h);for(let v=0;v<10;v++){const M=v/10*Math.PI*2+.16,S=new De;S.moveTo(0,0),S.bezierCurveTo(-1.8,2,-1.2,5.5,0,8),S.bezierCurveTo(.1,4.8,1.8,2,0,0),S.closePath();const E=new vi;E.moveTo(0,1.1),E.bezierCurveTo(.7,2.8,.05,4.8,0,6.1),E.bezierCurveTo(-.6,3.5,-.6,2,0,1.1),E.closePath(),S.holes.push(E);const C=new $r(S,30);C.rotateZ(M),C.rotateX(-Math.PI/2),C.translate(Math.sin(M)*8,.031,-21-Math.cos(M)*8),n.add(C,v%2===0?i:r)}const d=new De;d.moveTo(24,0),d.bezierCurveTo(17,.2,16,2.5,17.2,5.5),d.bezierCurveTo(18.1,8.5,17,10.8,13.8,12.9),d.bezierCurveTo(21.5,11.9,24,8.1,24.2,5.8),d.lineTo(25.6,.7),d.closePath();for(const v of[-1,1]){l(d,1.8,[0,0,-39],r,v<0);const M=new xt(d,{depth:.3,bevelEnabled:!0,bevelThickness:.11,bevelSize:.09,bevelSegments:3,curveSegments:36});M.scale(.86,.88,1),M.translate(3.1,.45,-36.95),v<0&&(M.scale(-1,1,1),Lv(M)),n.add(M,i),c([[v*23.7,1,-36.5],[v*20,2.2,-36.5],[v*19.5,5.7,-36.5],[v*20,8.8,-36.5],[v*17.3,11.1,-36.5]],.07),n.curve([[v*23,1,-36.35],[v*20.7,2.6,-36.35],[v*20.6,5.1,-36.35]],.036,h);for(const[S,E,C]of[[1.12,.13,o],[.94,.08,r],[.75,.05,a]]){const z=new at(S,E,8,64);z.scale(1,1.25,1),z.translate(v*20.4,5.8,-36.2),n.add(z,C)}n.add(new ft(.48,24,16).scale(.78,1.25,.35).translate(v*20.4,5.8,-36),u);for(let S=0;S<7;S++)n.box([.1,.24,.03],[v*(22.65-S*.22),2.2+S*.25,-36.22],h)}const f=new De;f.moveTo(-19,2.1),f.bezierCurveTo(-11,1.8,-5,4,0,4.2),f.bezierCurveTo(5,4,11,1.8,19,2.1),f.lineTo(18,1.3),f.bezierCurveTo(9,1.2,4,2.2,0,2.45),f.bezierCurveTo(-4,2.2,-9,1.2,-18,1.3),f.closePath(),l(f,.9,[0,0,-39.2],o),n.curve([[-18,2.05,-38.16],[-9,2.25,-38.16],[0,3.45,-38.16],[9,2.25,-38.16],[18,2.05,-38.16]],.065,i,72),n.add(new ft(.55,32,20).scale(1.5,.72,.5).translate(0,3.28,-37.9),u);for(const v of[-1,1]){n.curve([[v*1.1,3.3,-37.95],[v*2.2,4.05,-38],[v*4.6,3.3,-38.1]],.13,r,24);for(const M of[4.8,8.5,12.2])n.ring(.27,.04,[v*M,2.65,-38.1],i,!0)}const g=new De;g.moveTo(22.6,0),g.lineTo(26.6,0),g.bezierCurveTo(26.5,8,24,15,14,20),g.bezierCurveTo(19,15,21,9,21.4,5),g.closePath();for(const v of[-1,1])for(const M of[-10,-1]){l(g,2.1,[0,0,M],o,v<0);const S=new De;S.moveTo(24,0),S.bezierCurveTo(25,8,23,14,15,19),S.bezierCurveTo(21,14,22,8,22.5,0),S.closePath(),l(S,.25,[0,0,M+2.15],i,v<0),n.curve([[v*23.6,.5,M+2.52],[v*23.9,6,M+2.52],[v*21.3,12.5,M+2.52],[v*16.7,17.3,M+2.52]],.036,h,48),e.addFromCenter(new w(v*23.4,2.5,M+1),new w(2.2,5,2.2),"buttress")}for(const v of[-1,1]){n.curve([[v*23.6,.65,-37],[v*22.7,.8,-27],[v*22.8,.75,-15],[v*23.5,.7,-3]],.31,o,64),n.curve([[v*23.5,1,-37],[v*22.7,1.14,-27],[v*22.8,1.1,-15],[v*23.5,1.05,-3]],.045,i,64);for(const M of[-32,-23,-14]){const S=new De;S.moveTo(0,0),S.bezierCurveTo(.45,.7,.48,1.5,.15,2.2),S.lineTo(-.26,.9),S.closePath(),l(S,.26,[v*23,.4,M],i),n.add(new ft(.1,12,8).translate(v*23,1.1,M+.3),u)}}for(const[v,M,S]of[[-8.2,-27,6.6],[8.8,-29,4.8]]){const E=new De;E.moveTo(-1,0),E.bezierCurveTo(-.95,S*.3,-.7,S*.66,0,S),E.bezierCurveTo(.4,S*.66,1.05,S*.22,1,0),E.closePath(),l(E,.55,[v,0,M],r);const C=new xt(E,{depth:.17,bevelEnabled:!0,bevelSize:.06,bevelThickness:.06,bevelSegments:3,curveSegments:32});C.scale(.74,.85,1),C.translate(v,S*.06,M+.62),n.add(C,o),n.add(new ft(.3,24,16).scale(.75,1.8,.4).translate(v,S*.37,M+.87),u),n.curve([[v-.55,.5,M+.86],[v-.45,S*.35,M+.86],[v,S*.82,M+.86]],.035,i),n.curve([[v+.55,.5,M+.86],[v+.45,S*.35,M+.86],[v,S*.82,M+.86]],.035,i);for(let z=0;z<6;z++)n.box([.17,.055,.03],[v,S*.54+z*.13,M+.89],h);e.addFromCenter(new w(v,S/2,M+.35),new w(2,S,.9),"memory-pylon")}n.box([50,1.2,12],[0,17,-1],o);for(const v of[-1,1])n.box([2.4,5,1.2],[v*24.7,2.5,.2],o);for(const v of[-1,1]){n.box([19,16,1.2],[v*14.5,8,.2],o);for(let M=0;M<3;M++){const S=v*(8+M*6),E=new De;E.moveTo(S-2,1),E.lineTo(S+2,1),E.lineTo(S+2.4,12),E.lineTo(S,15),E.lineTo(S-2.4,12),E.closePath(),l(E,.18,[0,0,-.6],M===1?i:a),n.add(new qt(.23).scale(.6,1.6,.4).translate(S,8,-.8),u)}}for(const v of[-1,1])n.curve([[v*5.2,0,0],[v*5.1,5,0],[v*3.4,8,0],[0,10,0]],.58,i),n.curve([[v*4.8,.4,-.12],[v*4.7,4.7,-.12],[v*3.1,7.6,-.12],[0,9.5,-.12]],.055,h);n.finish();const x=Dv(s);t.add(x),t.userData.update=v=>x.userData.update(v);const p=new ve(new Gt(4.8,.6),new Ge({map:Vr(vu,""),transparent:!0,depthWrite:!1,toneMapped:!1}));p.position.set(0,1.82,-37.85),t.add(p);const m=new Bn(15779989,32,17,1.6);m.position.set(-2.5,5.5,-13),t.add(m);const _=new Bn(2653439,55,21,1.7);_.position.set(0,2.6,-17),t.add(_);for(const v of[-1,1]){const M=new Bn(2254301,65,23,1.7);M.position.set(v*20,5,-30),t.add(M)}return t.traverse(v=>{v instanceof ve&&(v.receiveShadow=!0,v.castShadow=!v.material.transparent)}),{group:t,setName(v){p.material.map?.dispose(),p.material.map=Vr(v,""),p.material.needsUpdate=!0}}}function Lv(s){if(s.index)for(let e=0;e<s.index.count;e+=3){const t=s.index.getX(e+1);s.index.setX(e+1,s.index.getX(e+2)),s.index.setX(e+2,t)}else for(const e of Object.values(s.attributes))for(let t=0;t<e.count;t+=3)for(let n=0;n<e.itemSize;n++){const i=e.array,r=(t+1)*e.itemSize+n,o=(t+2)*e.itemSize+n,a=i[r];i[r]=i[o],i[o]=a}}function Nv(s){const e=new Map,t=n=>{const i=e.get(n);if(i)return i;const r=n.clone(),o=n.onBeforeCompile.bind(n);return r.onBeforeCompile=(a,l)=>{o(a,l),a.vertexShader=`varying vec3 vHabitatWorld;
`+a.vertexShader,a.vertexShader=a.vertexShader.replace("#include <begin_vertex>",`#include <begin_vertex>
 vHabitatWorld=(modelMatrix*vec4(transformed,1.0)).xyz;`),a.fragmentShader=`varying vec3 vHabitatWorld;
`+a.fragmentShader,a.fragmentShader=a.fragmentShader.replace("#include <clipping_planes_fragment>",`#include <clipping_planes_fragment>
if((abs(vHabitatWorld.x)>31.55 && abs(vHabitatWorld.x)<82.3 && vHabitatWorld.y> -22.0 && vHabitatWorld.y<73.0 && vHabitatWorld.z>13.4 && vHabitatWorld.z<58.6) || (vHabitatWorld.x> -19.0 && vHabitatWorld.x<55.0 && vHabitatWorld.y> -1.1 && vHabitatWorld.y<36.0 && vHabitatWorld.z>57.7 && vHabitatWorld.z<118.7)) discard;`)},r.customProgramCacheKey=()=>n.customProgramCacheKey()+"/foundry-cavity-v1",r.userData.habitatClearance=!0,e.set(n,r),r};s.traverse(n=>{n instanceof ve&&(n.material=Array.isArray(n.material)?n.material.map(t):t(n.material))}),s.userData.habitatApertures={minAbsX:31.55,maxAbsX:82.3,minY:-22,maxY:73,minZ:13.4,maxZ:58.6}}function Uv(s,e){const t=new qe;t.name="solar-core-reference-chamber",t.userData.reference="https://bnetcmsus-a.akamaihd.net/cms/content_folder_media/r2/R2ENCXY6TTCZ1415234276295.jpg",t.userData.containmentState="closed-armoured-vessel";const n=new qe;n.name="solar-core-static-machinery",t.add(n);const i=new En(n),r=new En(t),o=(P,O,H=.48,Z=.72)=>{const W=new Ke({color:O,roughness:H,metalness:Z});return W.name=P,W},a=o("solar-core-olive-electrum",7828295,.43),l=o("solar-core-aged-lower-plates",8549195,.5),c=o("solar-core-burnished-seams",10589794,.37),h=o("solar-core-recessed-structure",1516074,.52),u=o("solar-core-vault-blue-steel",3884624,.51),d=o("solar-core-dark-alloy-deck",3490635,.64,.4),f=o("solar-core-deck-inset",2898242,.64,.4),g=new Ke({color:4953524,emissive:6209279,emissiveIntensity:2.1,metalness:.35,roughness:.24}),x=new Ke({color:1595007,emissive:1474261,emissiveIntensity:1.05,metalness:.12,roughness:.38});x.name="solar-core-blue-inspection-window";const p=new Ge({color:4289684}),m=new Ge({color:10610431}),_=(P,O,H,Z=n)=>{const W=new ve(O,H);return W.name=P,W.receiveShadow=!0,Z.add(W),W},v=(P,O,H,Z,W)=>{const $=new xt(P,{depth:O,steps:1,bevelEnabled:!0,bevelSize:.09,bevelThickness:.09,bevelSegments:2,curveSegments:28});return $.translate(H[0],H[1],H[2]-O/2),_(W,$,Z)};r.box([35.15,.018,39.1],[0,.014,98],d);for(let P=0;P<12;P++){const O=P*Math.PI/6,H=new De;H.absarc(0,0,15.2,O+.009,O+Math.PI/6-.009,!1),H.quadraticCurveTo(Math.cos(O+.33)*10,Math.sin(O+.33)*10,Math.cos(O+.22)*6.15,Math.sin(O+.22)*6.15),H.absarc(0,0,6.15,O+.22,O+.015,!0),H.closePath();const Z=new $r(H,36);Z.rotateX(-Math.PI/2),Z.translate(0,.033,100),r.add(Z,P%3===0?f:d);const W=[];for(let $=0;$<=24;$++){const le=6.2+$/24*8.8,he=O+.13*Math.sin($/24*Math.PI);W.push([Math.cos(he)*le,.051,100+Math.sin(he)*le])}r.curve(W,.018,h,32)}for(const P of[-1,1])r.curve([[P*3.7,.05,78.5],[P*3.7,.05,85],[P*6.3,.05,90],[P*9,.05,95]],.024,p,36),r.curve([[P*9,.05,95],[P*10.9,.05,103],[P*8.9,.05,111],[P*4,.05,116]],.02,c,40);for(const P of[81,93,109,116])for(const O of[-1,1]){const H=new De;H.moveTo(O*16.45,0),H.lineTo(O*17.5,0),H.bezierCurveTo(O*17.6,8,O*14.7,14.3,O*9,16.6),H.quadraticCurveTo(O*4.9,18.1,0,18.1),H.lineTo(0,16.75),H.quadraticCurveTo(O*5.8,16.7,O*9.8,14.5),H.bezierCurveTo(O*14.6,12,O*15.8,5.1,O*16.45,0),H.closePath(),v(H,1.35,[0,0,P],u,"solar-vault-curved-load-rib");const Z=new De;Z.moveTo(O*16.55,.5),Z.bezierCurveTo(O*16.4,7,O*13.9,13.4,O*8.8,15.4),Z.quadraticCurveTo(O*4.6,17,0,17.25),Z.lineTo(0,17.6),Z.quadraticCurveTo(O*5.6,17.4,O*9.2,15.8),Z.bezierCurveTo(O*14.4,13.8,O*16.9,7,O*16.9,.5),Z.closePath(),v(Z,.16,[0,0,P-.82],c,"solar-vault-inset-arch-band"),r.curve([[O*16.2,2,P-.96],[O*15.4,8,P-.96],[O*11.5,13.6,P-.96],[O*5.8,16.1,P-.96]],.027,p,40)}for(const P of[-1,1])for(const O of[96,111]){const H=new De;H.moveTo(0,0),H.bezierCurveTo(-3,2,-4,6,-3,10),H.quadraticCurveTo(-1.7,12,0,13.7),H.quadraticCurveTo(2.7,10.5,3.7,7),H.bezierCurveTo(4,3,2,1,0,0),H.closePath();const Z=new xt(H,{depth:.38,steps:1,bevelEnabled:!0,bevelSize:.1,bevelThickness:.1,bevelSegments:2,curveSegments:30});Z.rotateY(P<0?Math.PI/2:-Math.PI/2),Z.translate(P*17.15,1,O),i.add(Z,h),r.curve([[P*16.72,2,O],[P*16.73,5,O+1.5],[P*16.72,9,O+2],[P*16.72,13,O]],.07,c,36)}const M=new gt({side:Dt,depthWrite:!0,uniforms:{},vertexShader:`varying vec2 vUv;
#include <common>
#include <logdepthbuf_pars_vertex>
void main(){vUv=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);
#include <logdepthbuf_vertex>
}`,fragmentShader:`varying vec2 vUv;
#include <common>
#include <logdepthbuf_pars_fragment>
float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
void main(){
#include <logdepthbuf_fragment>
vec2 q=vUv*vec2(13.,6.);float cloud=.5+.25*sin(q.x+sin(q.y*1.8))+.2*sin(q.y*2.1+q.x*.7);vec2 cell=floor(vUv*vec2(190.,88.));float star=step(.996,hash(cell))*pow(max(0.,1.-length(fract(vUv*vec2(190.,88.))-.5)*2.),4.);vec3 c=mix(vec3(.006,.012,.022),vec3(.022,.055,.092),cloud)+star*vec3(.24,.36,.43);gl_FragColor=vec4(c,1.);
#include <tonemapping_fragment>
#include <colorspace_fragment>
}`});for(const P of[-1,1]){const O=new ve(new Gt(24,11),M);O.name="solar-core-bounded-star-depth-well",O.position.set(P*17.5,11.7,103),O.rotation.y=P<0?Math.PI/2:-Math.PI/2,t.add(O)}r.add(new et(5.4,5.7,.65,80).translate(0,.325,100),h),e.addCylinder(new w(0,.325,100),5.7,.65,{tag:"core-plinth",owner:"solar-core",part:"lower-plinth"}),r.add(new et(3.3,4.3,1.2,48).translate(0,1.2,100),l),e.addCylinder(new w(0,1.2,100),4.3,1.2,{tag:"core-plinth",owner:"solar-core",part:"upper-seat"}),i.add(new et(1.9,2.6,2.5,20).translate(0,2.75,100),h),i.add(new et(3.1,2.1,.65,24).translate(0,4.25,100),a);for(let P=0;P<6;P++){const O=P*Math.PI/3+.1,H=new De,Z=P===1||P===2,W=Z?4.25:5.4,$=Z?4.65:5.9;H.moveTo(1.6,.7),H.lineTo(4.8,.7),H.bezierCurveTo(6,1.7,6,3.2,5.2,W),H.lineTo(4.65,$),H.bezierCurveTo(5.1,3.2,4.3,2,2,1.7),H.closePath();const le=new xt(H,{depth:.85,steps:1,bevelEnabled:!0,bevelSize:.13,bevelThickness:.13,bevelSegments:3,curveSegments:24});le.translate(0,0,-.425),le.rotateY(O),le.translate(0,0,100),i.add(le,P%2?l:u)}const S=new w(0,10,100),E=new w(6.65,6.65,5.9),C=_("solar-core-armoured-containment",new ft(1,80,48),h);C.position.copy(S),C.scale.copy(E);const z=(P,O,H=0)=>{const Z=.12*Math.sin(O*2);return new w((E.x+H)*Math.sin(O)*Math.sin(P+Z),S.y+(E.y+H)*Math.cos(O),S.z-(E.z+H)*Math.sin(O)*Math.cos(P+Z))},T=(P,O,H,Z,W)=>{const $=[],le=[];for(let I=0;I<2;I++)for(let ce=0;ce<=10;ce++)for(let ae=0;ae<=9;ae++){const se=ce/10,de=ae/9,xe=H+(Z-H)*se,pe=.035*Math.sin(xe*2),F=P+(O-P)*de+pe,A=z(F,xe,I?0:.14);$.push(A.x,A.y,A.z)}for(let I=0;I<10;I++)for(let ce=0;ce<9;ce++){const ae=I*10+ce,se=ae+9+1;le.push(ae,ae+1,se,ae+1,se+1,se,110+ae,110+se,110+ae+1,110+ae+1,110+se,110+se+1)}const Ie=(I,ce)=>le.push(I,ce,I+110,ce,ce+110,I+110);for(let I=0;I<9;I++)Ie(I,I+1),Ie(10*10+I+1,10*10+I);for(let I=0;I<10;I++)Ie((I+1)*10,I*10),Ie(I*10+9,(I+1)*10+9);const ze=new je;ze.setAttribute("position",new Ae($,3)),ze.setIndex(le),ze.computeVertexNormals(),i.add(ze,W);const te=[];for(let I=0;I<=22;I++){const ce=H+(Z-H)*I/22,ae=z(P+.035*Math.sin(ce*2),ce,.175);te.push(ae.toArray())}r.curve(te,.025,c,28)};for(let P=0;P<10;P++)for(let O=0;O<3;O++){const H=(P%2?1:-1)*.035,Z=[.14,.98+H,1.93+H][O]+.006,W=[.98+H,1.93+H,3][O]-.006;T(P*Math.PI/5+.006,(P+1)*Math.PI/5-.006,Z,W,O===2?l:a)}const y=new De;y.moveTo(0,-4.7),y.bezierCurveTo(-1.5,-2.8,-2,1,-1.3,4.4),y.quadraticCurveTo(-.6,5.25,0,5.5),y.quadraticCurveTo(.6,5.25,1.3,4.4),y.bezierCurveTo(2,1,1.5,-2.8,0,-4.7),y.closePath();const b=new xt(y,{depth:.12,steps:1,bevelEnabled:!1,curveSegments:40}),D=b.getAttribute("position");for(let P=0;P<D.count;P++){const O=D.getX(P),H=D.getY(P),Z=-Math.sqrt(Math.max(.025,1-O*O/(6.8*6.8)-H*H/(6.8*6.8)))*6.08-D.getZ(P);D.setXYZ(P,O,10+H,100+Z)}for(let P=0;P<D.count;P+=3){const O=D.getX(P+1),H=D.getY(P+1),Z=D.getZ(P+1);D.setXYZ(P+1,D.getX(P+2),D.getY(P+2),D.getZ(P+2)),D.setXYZ(P+2,O,H,Z)}b.computeVertexNormals(),i.add(b,l);const L=_("solar-containment-diamond-crest",new qt(.4),g,t);L.position.set(0,14.45,95.4),L.scale.set(.7,1,.32);for(const P of[-.66,.66,2.5,3.8]){for(let O=0;O<10;O++){const H=z(P,1.08+O*.035,.2),Z=new lt(.07,.095,.04);Z.rotateY(-P),Z.translate(H.x,H.y,H.z),r.add(Z,O%3===0?m:g)}for(const O of[.53,1.9]){const H=z(P,O,.2);r.add(new ft(.075,10,6).translate(H.x,H.y,H.z),m)}}for(const P of[-.8,0,.8]){i.add(new et(.34,.38,1.35,16).translate(P,3.45,94.9),h),r.add(new ft(1,24,16).scale(.21,.45,.1).translate(P,3.5,94.51),x),i.add(new at(.245,.045,8,36).scale(1,1.9,.7).translate(P,3.5,94.4),c);for(const O of[2.72,4.16])i.add(new et(.38,.38,.13,16).translate(P,O,94.9),c)}const N=new De;N.moveTo(-1.8,.65),N.lineTo(-1.2,2.5),N.lineTo(1.2,2.5),N.lineTo(1.8,.65),N.lineTo(.9,.65),N.lineTo(.4,1.6),N.lineTo(-.4,1.6),N.lineTo(-.9,.65),N.closePath(),v(N,1.1,[0,0,94.9],l,"solar-inspection-manifold-fork"),i.box([4.25,.3,1.4],[0,2.5,94.9],a);for(let P=0;P<11;P++)r.box([.055,.55,.03],[(P-5)*.27,2.01,94.17],g);for(const P of[-1,1]){const O=new De;O.moveTo(P*6.2,0),O.lineTo(P*15.3,0),O.lineTo(P*15.3,1.65),O.quadraticCurveTo(P*11.2,2.5,P*6.2,1.1),O.closePath(),v(O,1.25,[0,0,112],h,"solar-low-service-wing");const H=new De;H.moveTo(P*6.3,1),H.quadraticCurveTo(P*11.2,2.35,P*15.3,1.55),H.lineTo(P*15.3,1.9),H.quadraticCurveTo(P*11.2,2.8,P*6.3,1.35),H.closePath(),v(H,1.4,[0,0,112],a,"solar-wing-armoured-brow"),r.add(new qt(.32).scale(1,1,.35).translate(P*12.5,1.66,111.2),g)}const B=new qe;B.name="solar-core-non-solid-energy-projection",B.userData.nonSolid=!0,t.add(B);const k=new Ge({color:7917311,transparent:!0,opacity:.28,depthWrite:!1,blending:Mn});for(let P=0;P<3;P++){const O=new ve(new at(.2,.01,5,36,Math.PI*1.3),k);O.position.set((P-1)*.8,3.5,94.39),O.rotation.y=.1,B.add(O)}i.finish(),r.finish(),e.addStaticMesh(n,{tag:"core-heart",owner:"solar-core",part:"static-containment-and-vault"});const q=(P,O,H,Z)=>{const W=new Bn(O,H,Z,2);W.position.set(...P),t.add(W)};q([0,7,90],14144951,280,26),q([0,4,93],6669823,23,11);for(const P of[-1,1])q([P*11,11,97],10137290,155,28),q([P*13,7,110],4159405,90,24);let U=0;const V=P=>{!Number.isFinite(P)||P<=0||(U+=Math.min(P,.1),B.children.forEach((O,H)=>{O.rotation.z=U*.8+H}),k.opacity=.23+Math.sin(U*1.7)*.055)};return t.userData.update=V,t.userData.clearApproaches=[[-9.1,98],[9.1,98],[0,86],[20,86]],{group:t,update:V}}function Ov(s,e){const t=new qe;t.name="inhabited-interior-rooms";const n=new En(t),i=[],r=(T,y,b=.35)=>{const D=new Ke({color:y,metalness:b,roughness:.57});return D.name=T,D},o=r("war-forge-bronze-deck",5523516,.55),a=r("robot-forge-blue-ceramic-deck",3428702),l=r("archive-ivory-ceramic",11380109,.18),c=r("core-slate-blue-deck",3360862,.45),h=r("interior-warm-stone-panels",7498848),u=r("solar-core-deep-navy",464687,.65);u.emissive.setHex(599902),u.emissiveIntensity=.6;const d=new Ge({color:4954574}),f=new Ge({color:12886887}),g=new Ge({color:8162476}),x=(T,y,b,D)=>{n.box(T,y,b),e.addFromCenter(new w(...y),new w(...T),D)},p=(T,y,b,D,L)=>x([y-T,1.2,D-b],[(T+y)/2,-.6,(b+D)/2],L,"floor"),m=(T,y,b,D,L)=>{const N=new Bn(b,D,L,2);N.name=T,N.position.set(...y),t.add(N)},_=(T,y,b,D,L=0)=>{const N=new ve(new Gt(D,D/4),new Ge({map:Vr(T,y,{width:1024,height:256,accent:"#c5ad7e"}),side:Dt}));N.position.set(...b),N.rotation.y=L,t.add(N)},v=(T,y,b,D,L=6,N=6)=>{const B=(V,P,O)=>D?[y+V,P,b+O]:[y+O,P,b+V],k=(V,P,O)=>D?[V,P,O]:[O,P,V],q={id:T,x:y,z:b,alongX:D,width:L,fraction:0,hold:0,leaves:[]};for(const V of[-1,1]){x(k(.36,N,.9),B(V*(L/2+.15),N/2,0),s.hull,"door-jamb"),n.box(k(.035,N-.2,.94),B(V*(L/2+.025),N/2,0),d),n.box(k(L/2+.25,N+.3,.12),B(V*(L*.75+.2),N/2,.34),s.wall);const P=new qe;P.name=T+(V<0?"-left-leaf":"-right-leaf");const O=new En(P);O.box(k(L/2,N,.26),[0,N/2,0],s.wall),O.box(k(L/2-.2,N-.3,.3),[0,N/2,0],h);for(const Z of[-1,1])O.box(k(.13,N-.5,.01),D?[V*(L/4-.15),N/2,Z*.155]:[Z*.155,N/2,V*(L/4-.15)],s.hull),O.box(k(.035,N*.56,.01),D?[-V*(L/4-.14),N/2,Z*.155]:[Z*.155,N/2,-V*(L/4-.14)],d),O.box(k(L/2-.6,.13,.01),D?[0,N*.75,Z*.155]:[Z*.155,N*.75,0],s.hull);O.finish(),t.add(P);const H={min:new w,max:new w,tag:"door:"+T};e.addBox(H),q.leaves.push({mesh:P,box:H,sign:V})}x(k(L+.6,.35,.9),B(0,N+.175,0),s.hull,"door-lintel"),n.box(k(L,.012,.8),B(0,.018,0),s.hull);const U=()=>{for(const V of q.leaves){const P=V.sign*(L/4+q.fraction*(L/2+.18));V.mesh.position.set(...B(P,0,0));const O=new w(...k(L/2,N,.32)).multiplyScalar(.5),H=new w(...B(P,N/2,0));V.box.min.copy(H).sub(O),V.box.max.copy(H).add(O)}};return U(),i.push(q),U},M=[],S=(T,y,b,D,L,N=[],B=.6,k=h)=>{const q=(V,P,O,H)=>{P<=V||H<=O||x(T?[P-V,H-O,B]:[B,H-O,P-V],T?[(V+P)/2,(H+O)/2,y]:[y,(H+O)/2,(V+P)/2],k,"interior-wall")};let U=b;for(const V of N)q(U,V.center-V.width/2,0,L),q(V.center-V.width/2,V.center+V.width/2,V.height,L),M.push(v(V.id,T?V.center:y,T?y:V.center,T,V.width,V.height)),U=V.center+V.width/2;q(U,D,0,L)};for(const T of[-1,1]){const y=T<0?-32:5.5,b=T<0?-5.5:32,D=T<0?o:a,L=T<0?f:d;S(!1,T*5.5,14,58,34,[{center:29,width:6,height:6,id:T<0?"war-fore":"robot-fore"},{center:43,width:6,height:6,id:T<0?"war-aft":"robot-aft"}],.3,s.wall),S(!1,T*32,14,58,34,[],.6,s.wall);for(const N of[14,58])S(!0,N,y,b,34,[],.6,s.wall);x([26.5,.5,44],[(y+b)/2,34.25,36],s.ceiling,"ceiling");for(let N=0;N<4;N++)for(let B=0;B<8;B++){const k=(b-y)/4,q=44/8;n.box([k-.09,.016,q-.1],[y+k*(N+.5),.015,14+q*(B+.5)],(N+B)%4===0?s.floor:D),T<0?n.box([.055,.009,q-.5],[y+k*(N+.5),.029,14+q*(B+.5)],s.hull):n.box([k-.5,.009,.045],[y+k*(N+.5),.029,14+q*(B+.5)],s.wallAccent)}for(const N of[19,36,53])n.box([.08,3.5,3.6],[T*5.69,10,N],s.hull),n.box([.1,2.5,2.8],[T*5.7,10,N],D),n.box([.13,.08,2.3],[T*5.71,10,N],L),n.box([.35,30,.6],[T*31.5,15,N],s.hull);for(const N of[25,46]){n.box([.16,20,12],[T*31.55,12,N],T<0?o:a);const B=new De;B.moveTo(-4,0),B.lineTo(-4.7,10),B.quadraticCurveTo(-4.2,16,0,19),B.quadraticCurveTo(4.2,16,4.7,10),B.lineTo(4,0),B.lineTo(0,2),B.closePath();const k=new xt(B,{depth:.22,bevelEnabled:!0,bevelSize:.08,bevelThickness:.05,bevelSegments:2,steps:1});k.rotateY(T<0?Math.PI/2:-Math.PI/2),k.translate(T*31.35,2,N),n.add(k,T<0?s.hull:s.wallAccent),n.box([.1,11,.16],[T*31.02,11,N],L),n.box([.24,.28,13],[T*31.2,4,N],s.hull)}for(const N of[29,43])_(T<0?"战争机械":"机器人装配","ASSEMBLY / SIDE ACCESS",[T*5.31,7.6,N],4,T<0?Math.PI/2:-Math.PI/2),n.box([3.6,.025,.07],[T*7.5,.043,N],L);m(T<0?"war-warm-service":"robot-cool-service",[T*10,7,36],T<0?14135931:9091287,130,34)}for(let T=16;T<58;T+=4)n.box([9.8,.018,3.9],[0,.022,T],c);for(const T of[-1,1])n.box([.06,.02,44],[T*3.9,.045,36],d);x([11,.4,44],[0,10.6,36],s.ceiling,"ceiling");for(const T of[22,38,52])n.box([7,.08,.4],[0,10.34,T],f),m("axis-downlight",[0,7.5,T],10270675,95,22);p(-6,6,58,78,c),S(!0,58,-5.5,5.5,10.8,[{center:0,width:7.2,height:7,id:"rear-transit"}],.7,s.wall);for(const T of[-1,1]){S(!1,T*6,58,78,11,[],.6,h),n.box([.075,.02,20],[T*3.8,.04,68],d);for(const y of[62,68,74])n.box([.08,5,1.1],[T*5.65,4,y],s.hull),n.box([.09,3.6,.18],[T*5.59,4,y],d)}for(let T=60;T<78;T+=4)n.box([7.2,.015,3.8],[0,.018,T],s.floor);x([12,.5,20],[0,11.25,68],s.ceiling,"ceiling"),m("rear-corridor-fill",[0,6,68],10138835,135,26),_("太阳核心 / 记忆资料室","SOLAR CORE / ARCHIVES",[0,8.2,57.57],5.8,Math.PI),p(-18,18,78,118,c),S(!0,78,-18,18,18,[{center:0,width:8,height:8,id:"core-entry"}],.8,s.wall),S(!0,118,-18,18,18,[],.8,s.wall),e.addFromCenter(new w(0,35,118),new w(36,70,.8),"sealed-sector"),S(!1,-18,78,118,18,[],.8,s.wall),S(!1,18,78,118,18,[{center:86,width:8,height:7,id:"archive-entry"}],.8,s.wall),x([36,.6,40],[0,18.3,98],s.ceiling,"ceiling");const E=Uv(s,e);t.add(E.group),n.box([7,8,.1],[0,4,117.5],s.hull),n.box([6.4,7.4,.12],[0,4,117.42],s.wall),n.box([.05,6.5,.14],[0,4,117.33],f),_("后部封存舱","SEALED / END OF INHABITED DECK",[0,9.6,117.3],6,Math.PI),_("太阳核心","SOLAR CORE / SYSTEM / USAGE",[0,10,78.45],7),p(18,22,82,90,l);for(const T of[82,90])S(!0,T,18,22,9,[],.5,h);x([4,.5,8],[20,9.25,86],s.ceiling,"ceiling");for(const T of[83,89])n.box([4,.02,.06],[20,.04,T],f);p(22,54,74,106,l),S(!1,22,74,106,12,[{center:86,width:8,height:7,id:"archive-inner"}],.6,h),S(!1,54,74,106,12,[],.6,h);for(const T of[74,106])S(!0,T,22,54,12,[],.6,h);x([32,.5,32],[38,12.25,90],s.ceiling,"ceiling");for(let T=0;T<8;T++)for(let y=0;y<8;y++)n.box([3.9,.012,3.9],[24+T*4,.02,76+y*4],(T+y)%3===0?h:l);for(const T of[26,38,50])n.box([.3,.24,30],[T,11.8,90],s.hull),n.box([.16,.06,25],[T,11.63,90],f);for(const T of[78,90,102])n.box([29,.24,.3],[38,11.8,T],s.hull);const C=(T,y,b)=>{const D=b?6:1.4,L=b?1.4:6;x([D,5.4,L],[T,2.7,y],s.wall,"archive-shelf");for(const N of[.3,1.7,3.1,4.5,5.5])n.box([D+.1,.12,L+.1],[T,N,y],s.hull);for(let N=0;N<5;N++)for(const B of[1,2.4,3.8]){const k=b?T+(N-2)*1.02:T-.77,q=b?y-.77:y+(N-2)*1.02;n.add(new qt(.35).scale(.55,1.35,.55).translate(k,B,q),g)}};for(const T of[28,38,48])C(T,75.6,!0);for(const T of[82,94,102])C(52.4,T,!1);x([6,.55,3],[38,.275,90],h,"archive-reading-island"),n.add(new qt(1.4).scale(.7,1.8,.7).translate(38,3,90),u),n.ring(1.8,.12,[38,1,90],s.hull);for(const T of[-1,1])x([4,.65,1],[38,.325,90+T*3.6],s.wallAccent,"archive-bench"),n.box([4,.09,1.1],[38,.69,90+T*3.6],s.hull);n.box([24,.02,.06],[34,.044,86],f),n.box([.06,.02,11],[27,.044,91.5],f),n.box([20,.02,.06],[37,.044,97],f),_("记忆资料室","ARCHIVES / CONFIGURATION / LOGS",[22.39,8.3,86],6,Math.PI/2);for(const T of[29,46])m("archive-warm-reading-light",[T,8,90],14930608,200,30);n.finish(),t.traverse(T=>{T instanceof ve&&(T.receiveShadow=!0)}),t.userData.layout={floorY:0,finalBoundaryZ:118,doorIds:i.map(T=>T.id),centralRoute:[-5.5,5.5,14,78]},t.userData.doors=i;const z=(T,y)=>{if(!Number.isFinite(T)||T<=0)return;const b=Math.min(T,.1);E.update(b),!(!y||![y.x,y.y,y.z].every(Number.isFinite))&&i.forEach((D,L)=>{const N=D.alongX?y.x-D.x:y.z-D.z,B=D.alongX?y.z-D.z:y.x-D.x,k=Math.abs(B)<6&&Math.abs(N)<D.width/2+1.2&&y.y<8,q=Math.abs(B)<1.2&&Math.abs(N)<D.width+dl&&y.y<8;D.hold=k||q?1.5:Math.max(0,D.hold-b);const U=D.hold>0?1:0;D.fraction=_t.clamp(D.fraction+(U?1:-1)*b*2.4,0,1),q&&(D.fraction=1),M[L]()})};return t.userData.update=z,{group:t,update:z}}function an(s,e){const t=s/2,n=new De,i=Math.min(.32,s*.2,e*.15);return n.moveTo(-t+i,0),n.lineTo(t-i,0),n.lineTo(t,i),n.lineTo(t,e*.72),n.quadraticCurveTo(t,e*.84,t*.68,e*.9),n.lineTo(t*.4,e),n.lineTo(-t*.4,e),n.lineTo(-t*.68,e*.9),n.quadraticCurveTo(-t,e*.84,-t,e*.72),n.lineTo(-t,i),n.closePath(),n}function Mr(s,e,t){const n=an(s,e),i=an(s-t*2,e-t*2).getPoints(10);return n.holes.push(new vi(i.reverse().map(r=>new Q(r.x,r.y+t)))),n}function Fv(s){const e=new De;return e.moveTo(-.62,s),e.lineTo(.62,s),e.lineTo(.62,s+.36),e.lineTo(.39,s+.7),e.lineTo(.39,7.35),e.bezierCurveTo(.39,8.65,.58,9.75,.96,10.6),e.lineTo(.96,11.88),e.lineTo(-.96,11.88),e.lineTo(-.96,10.6),e.bezierCurveTo(-.58,9.75,-.39,8.65,-.39,7.35),e.lineTo(-.39,s+.7),e.lineTo(-.62,s+.36),e.closePath(),e}function zv(){const s=new De;return s.moveTo(-15.65,11.98),s.lineTo(15.65,11.98),s.lineTo(15.65,8.85),s.lineTo(14.9,9.05),s.bezierCurveTo(12.25,10.85,7.2,11.28,0,11.3),s.bezierCurveTo(-7.2,11.28,-12.25,10.85,-14.9,9.05),s.lineTo(-15.65,8.85),s.closePath(),s}function kv(){const s=new De;return s.moveTo(-15.3,9.17),s.bezierCurveTo(-12.2,11.17,-7.1,11.55,0,11.55),s.bezierCurveTo(7.1,11.55,12.2,11.17,15.3,9.17),s.lineTo(15.3,9.4),s.bezierCurveTo(12.2,11.38,7.1,11.75,0,11.75),s.bezierCurveTo(-7.1,11.75,-12.2,11.38,-15.3,9.4),s.closePath(),s}function Bv(s,e){const t=new qe;t.name="archive-relief";const n=new En(t),i=new qe;i.name="archive-relief-couplings",i.userData.nonSolid=!0,t.add(i);const r=new En(i),o=Os(new Ke({color:s.wallAccent.color.clone().lerp(new Ne(9279901),.78),metalness:.43,roughness:.5,envMapIntensity:.48}),{roughnessVariation:.04,colourVariation:.018,relief:0});o.name="archive-relief-satin-silver";const a=Os(new Ke({color:s.wall.color.clone().lerp(new Ne(1587779),.68),metalness:.32,roughness:.62,envMapIntensity:.4}),{roughnessVariation:.04,colourVariation:.025,relief:0});a.name="archive-relief-deep-teal";const l=new Ge({color:4226982,toneMapped:!0});l.name="archive-relief-low-blue-coupling";const c=(g,x,p,m,_=0,v=.045,M=n)=>{const S=new xt(g,{depth:x,steps:1,curveSegments:10,bevelEnabled:v>0,bevelSize:v,bevelThickness:v,bevelSegments:1});S.rotateY(_),S.translate(...p),M.add(S,m)},h=(g,x,p,m,_)=>[g[0]+Math.cos(x)*p+Math.sin(x)*_,g[1]+m,g[2]-Math.sin(x)*p+Math.cos(x)*_];for(const g of[29.5,38,46.5]){const x=[g,.24,105.72],p=Math.PI;c(an(7.5,11.38),.22,x,a,p),c(Mr(7.5,11.38,.46),.66,h(x,p,0,0,.08),o,p,.07),c(Mr(6.4,10.28,.12),.13,h(x,p,0,.55,.26),s.hull,p,.025);for(const m of[-1.47,1.47]){c(an(2.54,7.05),.09,h(x,p,m,1.12,.215),s.wall,p,.035);for(let _=0;_<4;_++){const v=new De;v.moveTo(-.86,0),v.lineTo(.59,0),v.lineTo(.87,.18),v.lineTo(.87,.25),v.lineTo(-.62,.25),v.closePath(),c(v,.035,h(x,p,m,2.02+_*1.12,.308),a,p,.01)}}c(an(.64,1.14),.24,h(x,p,0,8.8,.2),s.hull,p,.025),c(an(.31,.66),.035,h(x,p,0,9.02,.445),l,p,.008,r)}for(const g of[77.1,98,104.4]){for(const x of[!1,!0]){const p=[x?53.72:22.28,0,g],m=x?-Math.PI/2:Math.PI/2,_=x&&g===104.4?5.94:.1;c(Fv(_),.91,p,o,m,.055),c(an(.46,10.4-_),.055,h(p,m,0,_+.6,.9),a,m,.025),c(an(.61,.88),.13,h(p,m,0,9.8,.94),s.hull,m,.025),c(an(.25,.43),.025,h(p,m,0,10.02,1.075),l,m,.008,r)}c(zv(),.78,[38,0,g-.39],o,0,.045);for(const x of[-1,1])c(kv(),.065,[38,0,g+x*.4],s.hull,0,.018)}const u=(g,x,p)=>{c(an(p,4.53),.16,g,a,x,.04),c(Mr(p,4.53,.29),.36,h(g,x,0,0,.1),o,x,.04),c(Mr(p-.82,3.69,.095),.07,h(g,x,0,.42,.18),s.hull,x,.015);for(const m of[-1,1]){const _=new De;_.moveTo(m*.5,1.06),_.lineTo(m*(p*.3),1.72),_.lineTo(m*(p*.3),1.89),_.lineTo(m*.5,1.23),_.closePath(),c(_,.04,h(g,x,0,0,.17),o,x,.01)}c(an(.42,.83),.07,h(g,x,0,2.47,.165),s.hull,x,.02),c(an(.18,.39),.025,h(g,x,0,2.66,.237),l,x,.006,r)};for(const g of[28,38,48])u([g,6.24,74.28],0,7.3);for(const g of[83.2,92])u([53.72,6.24,g],-Math.PI/2,6.9);u([22.28,6.24,98],Math.PI/2,5.2),n.finish(),r.finish();let d=0,f=0;return t.traverse(g=>{g instanceof ve&&(g.name="archive-relief-"+g.material.name,g.receiveShadow=!0,g.parent===i&&(g.userData.nonSolid=!0),d+=(g.geometry.index?.count??g.geometry.attributes.position.count)/3,f++)}),t.userData.geometryBudget={triangles:d,batches:f},t.userData.clearances={ceilingY:12,maxSideRelief:1.14,backWallMinZ:104.8,doorPocketZ:[78,94],terminalPositions:[[30,100],[46,100]]},e.addStaticMesh(t,{tag:"archive-relief",owner:"archive"}),t}function Vv(s,e=32){const t=new hn(s.map(a=>new w(a[0],a[1],a[2])),!1,"centripetal"),n=12,i=[],r=[];for(let a=0;a<=e;a++){const l=a/e,c=t.getPoint(l),h=t.getTangent(l),u=new w(0,1,0).cross(h).normalize(),d=h.clone().cross(u).normalize(),f=l*(s.length-1),g=Math.min(s.length-2,Math.floor(f)),x=f-g,p=_t.lerp(s[g][3],s[g+1][3],x),m=_t.lerp(s[g][4],s[g+1][4],x);for(let _=0;_<n;_++){const v=_/n*Math.PI*2,M=Math.cos(v),S=Math.sin(v),E=c.clone().addScaledVector(u,M*p).addScaledVector(d,Math.sign(S)*Math.pow(Math.abs(S),.75)*m);i.push(E.x,E.y,E.z)}}for(let a=0;a<e;a++)for(let l=0;l<n;l++){const c=a*n+l,h=a*n+(l+1)%n,u=c+n,d=h+n;r.push(c,h,u,h,d,u)}for(let a=1;a<n-1;a++){r.push(0,a+1,a);const l=e*n;r.push(l,l+a,l+a+1)}const o=new je;return o.setAttribute("position",new Ae(i,3)),o.setIndex(r),o.computeVertexNormals(),o}function Hv(s,e=null){const t=new Map,n=(g,x)=>{const p=g.index?g.toNonIndexed():g.clone();g.dispose(),p.deleteAttribute("uv");const m=t.get(x)??[];m.push(p),t.set(x,m)},i=(g,x="gold")=>n(Vv(g),x),r=(g,x,p="core")=>n(new ft(1,16,10).scale(x.x,x.y,x.z).translate(g.x,g.y,g.z),p),o=(g,x,p="bronze")=>n(new Si(new hn(g),24,x,5,!1),p),a=(g,x)=>g.map(([p,m,_,v,M])=>[p*x,m,_,v,M]);if(s==="phoenix"){i([[0,-.3,-19,.08,.12],[0,0,-11,3.3,1.6],[0,0,-2,5.3,2.3],[0,0,8,3.6,1.8],[0,0,17,.2,.3]]),i([[0,-1,-14,.1,.1],[0,-1.1,-1,4.7,1.45],[0,-.9,11,2.6,.9],[0,0,18,.05,.1]],"bronze");for(const g of[-1,1]){i(a([[4,0,7,2.1,1.2],[11,.1,5,4.5,1.3],[19,.8,-1,4.2,1.05],[22,1.5,-10,2.6,.65],[19,2,-20,1,.35],[13,2.3,-27,.05,.04]],g)),i(a([[7,1.08,6,1.2,.15],[12,1.38,3,2.35,.2],[18,1.8,-3,2.4,.17],[20,2.15,-10,1.2,.12],[18,2.35,-17,.03,.03]],g),"inlay"),o([[6,1.55,5],[12,1.9,2],[17,2.3,-4],[18.8,2.6,-11]].map(p=>new w(p[0]*g,p[1],p[2])),.12,"core"),i(a([[2,0,-5,1.5,1.1],[3,0,-14,1.7,.9],[1.4,-.3,-24,.03,.04]],g)),i(a([[5,-.6,3,1.9,1.2],[8,-.3,13,2.8,1.65],[8,.5,21,1.5,.85],[6.2,1,29,.04,.04]],g)),i(a([[7,1.25,11,1.2,.18],[8,1.5,17,1,.2],[6.5,1.55,26,.03,.03]],g),"inlay"),n(new at(1.25,.36,8,16).translate(g*7,-.65,17),"bronze"),r(new w(g*7,-.65,17.25),new w(1.04,1.04,.35),"core"),i(a([[7,-.65,17.5,.85,.85],[7,-.65,21,.6,.6],[7,-.65,26,.025,.025]],g),"engine");for(let p=0;p<3;p++)o([[g*(4+p*.5),1.8,2+p*2],[g*(6+p*.7),1.45,4+p*2]].map(m=>new w(...m)),.13)}r(new w(0,2,-5),new w(2.15,1.25,3.65),"bronze"),r(new w(0,2.7,-5.2),new w(1.55,.95,2.8),"core"),i([[0,1.8,-.6,.4,.4],[0,3.8,5,1.2,1.5],[0,3.3,10,.5,.7],[0,1.5,16,.04,.04]])}else{i([[0,0,-13,1.8,2.8],[0,0,-3,4,3.1],[0,0,7,3.7,2.7],[0,0,16,.2,.4]],"bronze");for(const g of[-1,1])i(a([[1.9,1.2,-25,.04,.04],[4,2,-16,2.1,2.1],[6,2.5,-4,3.6,2.3],[4,1.5,8,2.8,1.8],[2,1,15,.05,.05]],g)),i(a([[3.2,3,-17,.05,.05],[5.2,4,-7,1.4,.25],[4.6,3.2,3,1.5,.3],[3.2,2.5,9,.05,.05]],g),"inlay"),i(a([[3,0,1,1.2,1.1],[8,1,10,1.35,1.2],[11,5,17,1.65,1.5],[11,6,23,.6,.7]],g),"bronze"),i(a([[11,5,11,.1,.1],[12,6,18,2.6,2],[12,7,27,2,1.7],[10,8,36,.04,.04]],g)),i(a([[12,7.4,16,.1,.1],[12,8,23,1.2,.3],[10.8,8.5,32,.03,.03]],g),"inlay"),r(new w(g*11,5,18),new w(1.5,1.5,1),"core"),i(a([[11,5,21,1.1,1.1],[11,5,27,.9,.9],[11,5,32,.04,.04]],g),"engine"),r(new w(g*5.3,4.15,-2),new w(1.15,.4,1.6),"core"),o([[g*3,3,-18],[g*5,4.4,-8],[g*5.7,4.9,-3]].map(x=>new w(...x)),.18);n(new qt(3.9).scale(.8,.9,1.9).translate(0,-.9,-20),"core"),n(new at(3.6,.6,8,12).translate(0,-.9,-19),"gold"),r(new w(0,3,3),new w(1.5,.8,2.6),"core")}const l={gold:new Ke({color:12098128,roughness:.56,metalness:.64,envMap:e,envMapIntensity:.7,emissive:7033380,emissiveIntensity:.35}),bronze:new Ke({color:5718570,roughness:.65,metalness:.55,envMap:e,envMapIntensity:.5}),inlay:new Ke({color:1524316,roughness:.4,metalness:.42,emissive:615049,emissiveIntensity:.45}),core:new Ge({color:6014701,toneMapped:!1}),engine:new Ge({color:2526161,transparent:!0,opacity:.48,depthWrite:!1,toneMapped:!1})},c=[],h=new Lt;for(const[g,x]of t){const p=cs(x,!1);for(const m of x)m.dispose();p.computeBoundingBox(),h.union(p.boundingBox),c.push({geometry:p,material:l[g],finish:g})}const u=h.max.z-h.min.z,d=h.getCenter(new w);for(const g of c)g.geometry.translate(-d.x,-d.y,-d.z).scale(1/u,1/u,1/u),g.geometry.computeBoundingBox(),g.geometry.computeBoundingSphere();let f=!1;return{parts:c,dispose(){if(!f){f=!0;for(const g of c)g.geometry.dispose();for(const g of Object.values(l))g.dispose()}}}}const Ba=Math.PI*2,ys=s=>(s%1+1)%1;function Gv(s,e,t,n){const i=ys(e),r=4e-4;s.getPointAt(i,t);const o=s.getPointAt(ys(i-r)),l=s.getPointAt(ys(i+r)).sub(o).normalize(),c=s.getPointAt(ys(i-r*2)),h=s.getPointAt(ys(i+r*2)),u=t.clone().sub(c).normalize(),d=h.sub(t).normalize(),f=u.x*d.z-u.z*d.x,g=l.clone().cross(new w(0,1,0)).normalize(),x=l.clone().negate(),p=x.clone().cross(g).normalize();n.setFromRotationMatrix(new Fe().makeBasis(g,p,x));const m=.12+_t.clamp(f*22,-.17,.17)+Math.sin(i*Ba)*.025;n.multiply(new Pt().setFromAxisAngle(new w(0,0,1),m))}function Wv(s){const e=new qe;e.name="golden-fleet-patrols",s.updateWorldMatrix(!0,!0);const t=s.parent?.matrixWorld.clone()??new Fe,n=t.clone().invert(),i=new Lt().setFromObject(s).applyMatrix4(n),r=i.isEmpty()?100:i.max.y,o=new hl;o.layers.enableAll();const a=new w(0,-1,0).transformDirection(t),l=[];let c=0;const h=(T,y)=>(c++,o.set(new w(T,r+2e3,y).applyMatrix4(t),a),l.length=0,o.intersectObject(s,!0,l),l.length?l[0].point.clone().applyMatrix4(n).y:-1/0),u=(T,y,b,D,L,N,B)=>{const k=[];for(let P=0;P<12;P++){const O=P/12*Ba;k.push(new w(Math.sin(O)*T,0,b+Math.cos(O)*y))}const q=new hn(k,!0,"centripetal");q.arcLengthDivisions=768;let U=-1/0;for(let P=0;P<B;P++){const O=q.getPointAt(P/B);U=Math.max(U,h(O.x,O.z))}for(const P of[-70,70])U=Math.max(U,h(P,b+y));const V=Math.max(D,Number.isFinite(U)?U+L:D);for(let P=0;P<k.length;P++)k[P].y=V+Math.sin(P/k.length*Ba*2)*12;return q.updateArcLengths(),{curve:q,period:N,altitude:V,safety:L}},d=u(1050,1100,-1500,105,130,420,24),f=u(6500,2700,-8500,700,520,1050,16);let g=null;s.traverse(T=>{if(g||!(T instanceof ve))return;const y=Array.isArray(T.material)?T.material:[T.material];for(const b of y)if(b instanceof Ke&&b.envMap){g=b.envMap;break}});const x=new Map,p=new Map;for(const[T,y]of[["phoenix",6],["void-ray",2]]){const b=Hv(T,g);x.set(T,b);const D=b.parts.map(L=>{const N=new il(L.geometry,L.material,y);return N.name=T+"-"+L.finish,N.instanceMatrix.setUsage(rd),N.layers.set(1),N.frustumCulled=!1,N.castShadow=!1,N.receiveShadow=!1,e.add(N),N});p.set(T,D)}const m=[];for(let T=0;T<6;T++)m.push({kind:"phoenix",index:T,patrol:d,phase:T<3?T*.023:.5+(T-3)*.023,length:[68,60,64,70,58,64][T],altitudeOffset:T%3*7});for(let T=0;T<2;T++)m.push({kind:"void-ray",index:T,patrol:f,phase:.1+T*.48,length:310+T*45,altitudeOffset:T*140});const _=new w,v=new Pt,M=new w,S=new Fe;let E=0,C=!1;const z=T=>{if(!C){Number.isFinite(T)&&T>0&&(E=(E+Math.min(T,.1))%4200);for(const y of m){Gv(y.patrol.curve,E/y.patrol.period+y.phase,_,v),_.y+=y.altitudeOffset,M.setScalar(y.length),S.compose(_,v,M);for(const b of p.get(y.kind))b.setMatrixAt(y.index,S)}for(const y of p.values())for(const b of y)b.instanceMatrix.needsUpdate=!0}};return e.userData.patrols=[d,f],e.userData.flights=m.map(T=>({kind:T.kind,length:T.length,phase:T.phase,altitudeOffset:T.altitudeOffset})),e.userData.initializationRaycasts=c,e.userData.forwardKeepoutMetres=400,e.userData.coordinateSpace="hull-parent",e.userData.referenceTypes=["SC2 Phoenix","SC2 Void Ray"],z(0),{group:e,update:z,dispose(){if(!C){C=!0,e.removeFromParent();for(const T of p.values())for(const y of T)y.dispose();for(const T of x.values())T.dispose();e.clear()}}}}function Xv(){const s=[],e=[],t=[];for(let a=0;a<=32;a++){const l=a/32,c=Math.max(.001,(.72+.32*Math.sin(Math.min(1,l*2)*Math.PI))*Math.pow(Math.max(0,1-l),.7));for(let h=0;h<=24;h++){const u=h/24*Math.PI*2;s.push(Math.cos(u)*c,Math.sin(u)*c,l),e.push(h/24,l)}}for(let a=0;a<32;a++)for(let l=0;l<24;l++){const c=a*25+l,h=c+1,u=c+24+1,d=u+1;t.push(c,h,u,h,d,u)}for(let a=1;a<24;a++)t.push(0,a+1,a);const r=32*25;for(let a=1;a<24;a++)t.push(r,r+a,r+a+1);const o=new je;return o.setAttribute("position",new Ae(s,3)),o.setAttribute("uv",new Ae(e,2)),o.setIndex(t),o.computeVertexNormals(),o.computeBoundingBox(),o.computeBoundingSphere(),o}const Yv=`
  varying vec2 vPlumeUv;
  varying vec3 vPlumeNormal;
  varying vec3 vPlumeView;
  #include <common>
  #include <logdepthbuf_pars_vertex>
  void main() {
    vPlumeUv=uv;
    vec4 mvPosition=modelViewMatrix*vec4(position,1.0);
    vPlumeView=-mvPosition.xyz;
    vPlumeNormal=normalMatrix*normal;
    gl_Position=projectionMatrix*mvPosition;
    #include <logdepthbuf_vertex>
  }
`,qv=`
  uniform float uTime;
  uniform float uPower;
  uniform float uCore;
  varying vec2 vPlumeUv;
  varying vec3 vPlumeNormal;
  varying vec3 vPlumeView;
  #include <common>
  #include <logdepthbuf_pars_fragment>
  void main() {
    #include <logdepthbuf_fragment>
    // MSAA extrapolates varyings: clamp BEFORE powers, angles and exp.
    vec2 st=clamp(vPlumeUv,vec2(0.0),vec2(1.0));
    float angle=clamp(st.x*6.2831853,0.0,6.2831853);
    float t=clamp(st.y,0.0,1.0);
    vec3 n=vPlumeNormal/max(length(vPlumeNormal),0.00001);
    vec3 v=vPlumeView/max(length(vPlumeView),0.00001);
    float facing=clamp(abs(dot(n,v)),0.0,1.0);
    float edge=pow(clamp(facing,0.0,1.0),0.65);
    float fade=exp(-clamp(t*4.3,0.0,12.0))*(1.0-smoothstep(0.66,1.0,t));
    float throat=smoothstep(0.0,0.035,t);
    float flow=0.93+0.07*sin(clamp(t*23.0-angle*2.0-uTime*1.7,-100000.0,100000.0));
    float breath=0.96+0.04*sin(uTime*0.8);
    vec3 cold=vec3(0.055,0.29,0.80);
    vec3 hot=mix(vec3(0.20,0.63,0.98),vec3(0.70,0.88,1.0),uCore);
    vec3 color=mix(hot,cold,smoothstep(0.02,0.72,t));
    float alpha=clamp(mix(0.37,0.76,uCore)*fade*throat*flow*breath*edge*(0.75+0.25*uPower),0.0,0.82);
    if(alpha<0.002)discard;
    gl_FragColor=vec4(clamp(color,vec3(0.0),vec3(1.0)),alpha);
    #include <colorspace_fragment>
  }
`;function jv(s){const e=new qe;e.name="ark-engine-exhaust",e.userData.coordinateSpace="hull-parent",e.userData.excludedFromPhysicalBounds=!0;const t=Xv(),n={value:0},i={value:.5},r=x=>new gt({uniforms:{uTime:n,uPower:i,uCore:{value:x}},vertexShader:Yv,fragmentShader:qv,transparent:!0,depthWrite:!1,depthTest:!0,side:wn,blending:Qn,toneMapped:!1}),o=r(0),a=r(1),l=[];let c=!1,h=!1,u=0,d=.5;const f=()=>{const x=s.userData.engineExhausts;if(!Array.isArray(x)||x.length===0)return;const p=x.filter(S=>S&&Array.isArray(S.position)&&S.position.length===3&&S.position.every(Number.isFinite)&&Array.isArray(S.direction)&&S.direction.length===3&&S.direction.every(Number.isFinite)&&Number.isFinite(S.radius)&&S.radius>0&&Math.hypot(...S.direction)>1e-8);if(!p.length)return;s.updateWorldMatrix(!0,!0);const _=(s.parent?.matrixWorld.clone().invert()??new Fe).multiply(s.matrixWorld),v=new w().setFromMatrixScale(_),M=(Math.abs(v.x)+Math.abs(v.y)+Math.abs(v.z))/3;for(let S=0;S<p.length;S++){const E=p[S],C=new qe;C.name="ark-plume-"+S;const z=new w(...E.direction).transformDirection(_),T=E.radius*M,y=T*13.5;C.position.set(...E.position).applyMatrix4(_).addScaledVector(z,T*.06),C.quaternion.setFromUnitVectors(new w(0,0,1),z);const b=new ve(t,o),D=new ve(t,a);b.name="fading-blue-volume",D.name="blue-white-throat",D.scale.set(.43,.43,.3);for(const L of[b,D])L.layers.set(1),L.frustumCulled=!0,L.renderOrder=2,C.add(L);e.add(C),l.push({root:C,radius:T,length:y,phase:S*.83})}c=!0,e.userData.metadataReady=!0,e.userData.nozzleCount=l.length},g=(x,p=.5)=>{if(h)return;c||f();const m=Number.isFinite(x)?_t.clamp(x,0,.1):0,_=Number.isFinite(p)?_t.clamp(p,0,1):.5;u=(u+m)%(Math.PI*20),n.value=u,d+=(_-d)*(1-Math.exp(-m*1.4)),i.value=d;for(const v of l){const M=1+.025*Math.sin(u*.8+v.phase);v.root.scale.set(v.radius,v.radius,v.length*(.72+.48*d)*M)}};return e.userData.metadataReady=!1,g(0),{group:e,get metadataReady(){return c},update:g,dispose(){h||(h=!0,e.removeFromParent(),e.clear(),l.length=0,t.dispose(),o.dispose(),a.dispose())}}}function Kv(s,e,t){const n=new qe;n.name="ark-inhabited-enclave";const i=Tv(),r=new En(n),o=i.hull;i.wallAccent;const a=i.wall,l=i.trim,c=(B,k,q,U="architecture")=>{r.box(B,k,q),e.addFromCenter(new w(...k),new w(...B),U)},h=wv.map(B=>({id:B.id,label:B.label,description:B.description,deck:0,min:new w(B.bounds[0],0,B.bounds[2]),max:new w(B.bounds[1],18,B.bounds[3])}));c([48,1.2,42],[0,-.6,-21],i.floor,"floor"),c([10,1.2,14],[0,-.6,7],i.floor,"floor"),c([64,1.2,44],[0,-.6,36],i.floor,"floor");const u=(B,k,q)=>e.addFromCenter(new w(...k),new w(...B),q);for(const B of[-1,1]){u([.28,24,42],[B*24,12,-21],"shield"),u([.4,40,44],[B*32,20,36],"foundry-rail"),u([19,20,.6],[B*14.5,10,0],"rear-bulkhead"),u([27,40,.6],[B*18.5,20,14],"foundry-bulkhead"),c([.6,10,14],[B*5,5,7],a,"corridor-wall"),r.box([.07,.04,14],[B*3.7,.055,7],l);for(const k of[1,7,13])r.curve([[B*4.8,0,k],[B*4.7,5,k],[B*3,8,k],[0,10,k]],.24,o),r.curve([[B*4.5,.4,k],[B*4.4,4.8,k],[B*2.8,7.7,k]],.022,l)}u([48,24,.28],[0,12,-42],"shield"),u([48,.2,42],[0,24,-21],"shield-roof"),c([10,.6,14],[0,10,7],a,"ceiling"),r.finish();const d=Iv(i,e);n.add(d.group),e.addStaticMesh(d.group,{tag:"bridge-structure",owner:"sanctum",filter:B=>(Array.isArray(B.material)?B.material:[B.material]).some(q=>q instanceof Ke&&!q.transparent&&q!==i.trim)});const f=Ov(i,e);n.add(f.group),n.add(Bv(i,e)),n.traverse(B=>{B instanceof ve&&(B.receiveShadow=!0)});const g=Cv(i),x=new Lt().setFromObject(g),p=x.getSize(new w),m=new w(Cs.width,Cs.height,Cs.length);g.scale.copy(m.divide(p));const _=g.userData.mountPoint,v=new w(..._??[0,0,-300]);g.position.copy(v.multiply(g.scale).negate()),g.position.y-=1.25,g.updateMatrixWorld(!0),Nv(g);const M=new Lt().setFromObject(g);g.traverse(B=>B.layers.set(1)),n.add(g);const S=new ws(16772046,1.9);S.position.set(-1,2,-1.2),S.layers.set(1),S.userData.exteriorOnly=!0,S.visible=!1,n.add(S);const E=new ws(9357055,.95);E.position.set(2,.5,1),E.layers.set(1),E.userData.exteriorOnly=!0,E.visible=!1,n.add(E);const C=new Ua(10201276,1186345,.6);C.layers.set(1),C.userData.exteriorOnly=!0,C.visible=!1,n.add(C);const z=Wv(g),T=jv(g);n.add(z.group,T.group),n.userData.update=(B,k,q=.55)=>{d.group.userData.update(B),k&&f.update(B,k),z.update(B),T.update(B,q)};const y=(B,k,q,U,V=0)=>{const P=new ve(new Gt(U,U*.25),new Ge({map:Vr(B,k,{width:1024,height:256,accent:"#d3b77c"}),side:wn})),O=new ve(P.geometry,P.material);return O.rotation.y=Math.PI,O.position.z=-.015,P.add(O),P.position.set(...q),P.rotation.y=V,n.add(P),P};y("战争机械装配车间","WAR COUNCIL / MECHANICAL FORGE",[-18,3.2,14.8],5.5,Math.PI),y("机器人装配车间","AUTOMATON ASSEMBLY",[18,3.2,14.8],5.5,Math.PI);const b=new Map;for(const B of Sv){const k=h.find(U=>U.id===B.room),q=new w((k.min.x+k.max.x)/2+B.offset[0],0,(k.min.z+k.max.z)/2+B.offset[1]);b.set(B.id,{spec:B,position:q,yaw:B.yaw,roomLabel:k.label,deck:0})}n.add(new Ua(5402257,527120,.48));const D=new ws(13097189,.85);D.position.set(-80,150,-120),n.add(D),D.castShadow=!0,D.shadow.mapSize.set(2048,2048),Object.assign(D.shadow.camera,{left:-75,right:75,top:95,bottom:-95,near:1,far:350}),D.shadow.bias=-3e-4,D.shadow.normalBias=.035;const L=new ws(3763952,.9);L.position.set(80,40,50),n.add(L);const N=new Bn(3896543,38,45,1.7);return N.position.set(0,9,-21),n.add(N),s.add(n),{group:n,materials:i,rooms:h,anchors:b,ladders:[],spawn:new w(0,.08,-11.5),spawnYaw:0,hullBounds:M,setName(B){d.setName(B)},dispose(){z.dispose(),T.dispose(),n.remove(z.group,T.group),s.remove(n),ru(n)}}}function ru(s){const e=new Set,t=new Set,n=new Set;s.traverse(i=>{const r=i;if(r.geometry&&e.add(r.geometry),r.material)for(const o of Array.isArray(r.material)?r.material:[r.material])t.add(o)});for(const i of t){for(const r of Object.values(i))r instanceof It&&n.add(r);i.dispose()}for(const i of n)i.dispose();for(const i of e)i.dispose()}function Zv(s,e){return s.find(t=>e.x>=t.min.x&&e.x<=t.max.x&&e.z>=t.min.z&&e.z<=t.max.z&&e.y>=-.5&&e.y<t.max.y)??null}const Zn=126e3/1060,Jv=165e4,Ho=15e5,ml=`
float hash3(vec3 p) {
  p = fract(p * 0.1031);
  p += dot(p, p.yzx + 33.33);
  return fract((p.x + p.y) * p.z);
}
float noise3(vec3 p) {
  vec3 i = floor(p), f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  return mix(mix(mix(hash3(i), hash3(i + vec3(1,0,0)), f.x),
                 mix(hash3(i + vec3(0,1,0)), hash3(i + vec3(1,1,0)), f.x), f.y),
             mix(mix(hash3(i + vec3(0,0,1)), hash3(i + vec3(1,0,1)), f.x),
                 mix(hash3(i + vec3(0,1,1)), hash3(i + vec3(1,1,1)), f.x), f.y), f.z);
}
float fbm(vec3 p) {
  float sum = 0.0, amplitude = 0.52;
  mat3 turn = mat3(0.0,0.8,0.6, -0.8,0.36,-0.48, -0.6,-0.48,0.64);
  for (int i = 0; i < 5; i++) {
    sum += amplitude * noise3(p);
    p = turn * p * 2.04 + vec3(7.1,3.4,1.7);
    amplitude *= 0.49;
  }
  return sum;
}
`,$v=`
#include <common>
#include <logdepthbuf_pars_vertex>
varying vec3 vDirection;
void main() {
  vDirection = normalize(position);
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  #include <logdepthbuf_vertex>
  // At near=0.1 / far=2e6, ordinary projected Z rounds past W for some
  // million-metre sphere vertices. Log depth only fixes fragment depth, not
  // homogeneous clipping. This background never writes/tests depth, so keep
  // Z safely inside the clip volume instead of xyww (exactly on its edge).
  gl_Position.z = 0.0;
}
`,Qv=ml+`
#include <logdepthbuf_pars_fragment>
varying vec3 vDirection;
uniform vec3 uNebulaA;
uniform vec3 uNebulaB;
uniform float uSeed;
void main() {
  #include <logdepthbuf_fragment>
  vec3 d = normalize(vDirection);
  vec3 p = d * 2.5 + vec3(uSeed * 0.17);
  float broad = fbm(p);
  float wisps = fbm(p * 2.1 + vec3(broad * 1.8, broad, 0.0));
  float band = exp(-pow((d.y + d.x * 0.35 - d.z * 0.12 + (broad - 0.5) * 0.65) * 2.2, 2.0));
  float clouds = smoothstep(0.23, 0.74, wisps) * band;
  float dust = smoothstep(0.48, 0.7, fbm(p * 4.0)) * band;
  vec3 color = vec3(0.0015, 0.003, 0.009);
  color += mix(uNebulaA, uNebulaB, smoothstep(0.32,0.68,broad)) * clouds * 0.25;
  color += vec3(0.009,0.018,0.045) * band * broad;
  color *= 1.0 - dust * 0.58;
  gl_FragColor = vec4(color, 1.0);
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}
`,ex=`
#include <common>
#include <logdepthbuf_pars_vertex>
attribute float aSize;
attribute vec3 aColor;
varying vec3 vColor;
void main() {
  vColor = aColor;
  vec4 view = modelViewMatrix * vec4(position,1.0);
  gl_Position = projectionMatrix * view;
  #include <logdepthbuf_vertex>
  // Preserve vFragDepth from the true view-space distance for planet/ship
  // occlusion, but avoid imprecise hardware far-plane clipping of the stars.
  #ifdef USE_LOGDEPTHBUF
    gl_Position.z = 0.0;
  #endif
  gl_PointSize = aSize;
}
`,tx=`
#include <logdepthbuf_pars_fragment>
varying vec3 vColor;
void main() {
  #include <logdepthbuf_fragment>
  float r = length(gl_PointCoord - 0.5) * 2.0;
  if (r > 1.0) discard;
  float core = exp(-r*r*8.0);
  float halo = 0.16 * pow(1.0-r,2.0);
  gl_FragColor = vec4(vColor, core + halo);
  #include <colorspace_fragment>
}
`,Go=`
#include <common>
#include <logdepthbuf_pars_vertex>
varying vec3 vLocal;
varying vec3 vNormal;
varying vec3 vWorld;
void main() {
  vLocal = normalize(position);
  vNormal = normalize(mat3(modelMatrix) * normal);
  vWorld = (modelMatrix * vec4(position,1.0)).xyz;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0);
  #include <logdepthbuf_vertex>
}
`,nx=ml+`
#include <logdepthbuf_pars_fragment>
varying vec3 vLocal;
varying vec3 vNormal;
varying vec3 vWorld;
uniform vec3 uSun;
uniform vec3 uOcean;
uniform float uSeed;
void main() {
  #include <logdepthbuf_fragment>
  vec3 p = normalize(vLocal);
  vec3 n = normalize(vNormal), view = normalize(cameraPosition-vWorld);
  vec3 terrain = p * 2.7 + vec3(uSeed*0.09);
  float large = fbm(terrain);
  float continent = smoothstep(0.52,0.62,large);
  float coast = smoothstep(0.46,0.55,large) - continent;
  vec3 surface = uOcean * (0.72 + 0.38*large);
  surface = mix(surface, vec3(0.065,0.14,0.145), continent * 0.84);
  surface += vec3(0.01,0.047,0.052) * coast;
  float polar = smoothstep(0.80,0.96,abs(p.y) + (large-0.5)*0.16);
  surface = mix(surface,vec3(0.51,0.66,0.73),polar*0.82);
  // Coherent, stretched cloud fronts instead of unrelated low-resolution speckles.
  vec3 cloudDomain = vec3(p.x*4.0 + sin(p.y*8.0)*0.45,p.y*8.0,p.z*4.0);
  float cloudFlow = fbm(cloudDomain + vec3(uSeed*0.05,0.0,0.0));
  float clouds = smoothstep(0.46,0.69,cloudFlow);
  clouds *= 0.65 + 0.35*sin(p.y*11.0 + large*4.0);
  surface = mix(surface,vec3(0.67,0.77,0.84),clouds*0.86);
  float sun = dot(n,normalize(uSun));
  float daylight = smoothstep(-0.12,0.6,sun);
  vec3 color = surface * (0.055 + daylight*1.05);
  float rim = pow(1.0-max(dot(n,view),0.0),3.5);
  color += vec3(0.07,0.32,0.68) * rim * (0.16+daylight*0.6);
  vec3 halfDir = normalize(normalize(uSun)+view);
  float glint = pow(max(dot(n,halfDir),0.0),70.0) * (1.0-clouds)*(1.0-continent);
  color += vec3(0.25,0.44,0.58) * glint*0.45;
  gl_FragColor = vec4(color,1.0);
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}
`,ix=`
#include <logdepthbuf_pars_fragment>
varying vec3 vNormal;
varying vec3 vWorld;
uniform vec3 uSun;
void main() {
  #include <logdepthbuf_fragment>
  vec3 n = normalize(vNormal), view = normalize(cameraPosition-vWorld);
  float rim = pow(1.0-clamp(abs(dot(n,view)),0.0,1.0),5.0);
  float light = smoothstep(-0.3,0.8,dot(n,normalize(uSun)));
  gl_FragColor = vec4(vec3(0.15,0.43,0.88),rim*(0.13+light*0.52));
  #include <colorspace_fragment>
}
`,sx=ml+`
#include <logdepthbuf_pars_fragment>
varying vec3 vLocal;
varying vec3 vNormal;
uniform vec3 uSun;
void main() {
  #include <logdepthbuf_fragment>
  float mare = smoothstep(0.32,0.63,fbm(normalize(vLocal)*3.0));
  vec3 surface = mix(vec3(0.16,0.20,0.26),vec3(0.39,0.43,0.48),mare);
  float light = smoothstep(-0.08,0.85,dot(normalize(vNormal),normalize(uSun)));
  gl_FragColor = vec4(surface*(0.045+light),1.0);
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}
`,rx=`
varying vec2 vUv;
void main() { vUv = uv; gl_Position = vec4(position.xy,0.0,1.0); }
`,ox=`
varying vec2 vUv;
uniform float uWarp;
uniform float uTime;
uniform float uAspect;
void main() {
  vec2 p = (vUv-0.5)*vec2(uAspect,1.0);
  float r = length(p);
  float angle = atan(p.y,p.x);
  float ray = pow(max(sin(angle*91.0 + sin(angle*17.0)*4.0),0.0),28.0);
  float travel = pow(max(sin(r*28.0-uTime*16.0+angle*7.0),0.0),6.0);
  float veil = smoothstep(0.08,0.65,r);
  float alpha = uWarp * (ray*travel*veil*0.7 + veil*0.06);
  gl_FragColor = vec4(vec3(0.22,0.61,0.93),alpha);
}
`;class $c{constructor(e,t,n){this.scene=e,this.camera=t,this.quality=n.quality,this.seed=n.seed??Math.random()*1e4,this.randomState=Math.floor(this.seed*104729)>>>0||1,this.root.name="space-environment",this.skyMaterial=new gt({vertexShader:$v,fragmentShader:Qv,side:Ht,depthWrite:!1,depthTest:!1,uniforms:{uSeed:{value:this.seed},uNebulaA:{value:new Ne(.08,.16,.36)},uNebulaB:{value:new Ne(.22,.1,.32)}}}),this.sky=new ve(new ft(Jv,32,20),this.skyMaterial),this.sky.name="space-sky",this.sky.frustumCulled=!1,this.sky.renderOrder=-20,this.stars=this.createStars(),this.root.add(this.sky,this.stars),this.planetMaterial=new gt({vertexShader:Go,fragmentShader:nx,uniforms:{uSun:{value:this.sunlight},uSeed:{value:this.seed},uOcean:{value:new Ne(.026,.105,.27)}}}),this.planet=new ve(new ft(126e3,80,56),this.planetMaterial),this.planet.name="space-planet",this.planet.position.set(-145e3,55e3,-315e3);const i=new gt({vertexShader:Go,fragmentShader:ix,uniforms:{uSun:{value:this.sunlight}},side:Ht,transparent:!0,blending:Mn,depthWrite:!1});this.atmosphere=new ve(new ft(1085*Zn,64,48),i),this.atmosphere.name="space-atmosphere",this.atmosphere.position.copy(this.planet.position),this.atmosphere.renderOrder=2,this.moon=new ve(new ft(225*Zn,40,28),new gt({vertexShader:Go,fragmentShader:sx,uniforms:{uSun:{value:this.sunlight}}})),this.moon.name="space-moon",this.moon.position.set(1720,1050,-6200).multiplyScalar(Zn),this.root.add(this.planet,this.atmosphere,this.moon),this.sunLight=new ws(14214399,.72),this.sunLight.position.copy(this.sunlight).multiplyScalar(4e3*Zn),this.ambient=new Ua(5599895,1053726,.24),this.root.add(this.sunLight,this.ambient),this.asteroids=this.createAsteroids(),this.root.add(this.asteroids),this.warpMaterial=new gt({vertexShader:rx,fragmentShader:ox,transparent:!0,blending:Mn,depthWrite:!1,depthTest:!1,uniforms:{uWarp:{value:0},uTime:{value:0},uAspect:{value:t.aspect}}}),this.warpOverlay=new ve(new Gt(2,2),this.warpMaterial),this.warpOverlay.name="space-warp",this.warpOverlay.frustumCulled=!1,this.warpOverlay.renderOrder=999,this.warpOverlay.visible=!1,t.add(this.warpOverlay),t.parent||e.add(t),e.add(this.root),e.fog=null}root=new qe;sky;skyMaterial;stars;planet;planetMaterial;atmosphere;moon;asteroids;warpOverlay;warpMaterial;sunLight;ambient;sunlight=new w(-.6,.65,.8).normalize();quality;seed;randomState;warpState="idle";warpTimer=0;elapsed=0;onArrive=null;disposed=!1;random(){return this.randomState=Math.imul(this.randomState,1664525)+1013904223>>>0,this.randomState/4294967296}createStars(){const e=Math.min(6500,Math.max(1800,this.quality.starCount)),t=new Float32Array(e*3),n=new Float32Array(e*3),i=new Float32Array(e);for(let a=0;a<e;a++){const l=this.random()*2-1,c=this.random()*Math.PI*2,h=Math.sqrt(1-l*l);t.set([Math.cos(c)*h*Ho,l*Ho,Math.sin(c)*h*Ho],a*3);const u=this.random();i[a]=u>.988?3.7:u>.9?2.2:1.2;const d=this.random()>.8,f=.55+u*.45;n.set(d?[f,f*.84,f*.65]:[f*.7,f*.85,f],a*3)}const r=new je;r.setAttribute("position",new kt(t,3)),r.setAttribute("aColor",new kt(n,3)),r.setAttribute("aSize",new kt(i,1));const o=new ol(r,new gt({vertexShader:ex,fragmentShader:tx,transparent:!0,depthWrite:!1,blending:Mn}));return o.name="space-stars",o.frustumCulled=!1,o.renderOrder=-19,o}createAsteroids(){const e=new zs(1,2),t=e.getAttribute("position");for(let r=0;r<t.count;r++){const o=t.getX(r),a=t.getY(r),l=t.getZ(r),c=1+.1*Math.sin(o*5+a*3)*Math.cos(l*4-o*2)+.05*Math.sin(a*7+l*3);t.setXYZ(r,o*c,a*c*.82,l*c*.92)}e.computeVertexNormals();const n=Math.min(16,Math.max(6,Math.floor(this.quality.asteroidCount/21))),i=new il(e,new Ke({color:7502212,roughness:.97,metalness:.02}),n);return i.name="space-distant-asteroids",i.frustumCulled=!1,this.placeAsteroids(i),i}placeAsteroids(e){const t=new Mt;for(let n=0;n<e.count;n++)t.position.set((n%2?1:-1)*(2300+this.random()*2e3),-1200+this.random()*1900,-500+this.random()*4200).multiplyScalar(Zn),t.rotation.set(this.random()*6,this.random()*6,this.random()*6),t.scale.setScalar((8+this.random()*19)*Zn),t.updateMatrix(),e.setMatrixAt(n,t.matrix);e.instanceMatrix.needsUpdate=!0}triggerWarp(e){return this.disposed||this.warpState!=="idle"?!1:(this.warpState="charging",this.warpTimer=0,this.onArrive=e??null,this.warpOverlay.visible=!0,!0)}get warping(){return this.warpState!=="idle"}get warpPhase(){return this.warpState}get phase(){return this.warpState}get nebulaColors(){return[this.skyMaterial.uniforms.uNebulaA.value.getHex(),this.skyMaterial.uniforms.uNebulaB.value.getHex()]}reroll(){if(this.disposed)return;this.seed=this.random()*1e4,this.skyMaterial.uniforms.uSeed.value=this.seed,this.planetMaterial.uniforms.uSeed.value=this.seed;const e=this.random();this.skyMaterial.uniforms.uNebulaA.value.setRGB(.055+e*.04,.12+e*.04,.31+e*.08),this.skyMaterial.uniforms.uNebulaB.value.setRGB(.17+e*.08,.08+e*.045,.28+e*.07),this.planetMaterial.uniforms.uOcean.value.setRGB(.022,.085+this.random()*.045,.23+this.random()*.08),this.planet.position.set(-1150+this.random()*1300,550+this.random()*650,-4100-this.random()*900).multiplyScalar(Zn),this.planet.rotation.set(this.random()*.3,this.random()*Math.PI*2,.08),this.atmosphere.position.copy(this.planet.position),this.moon.position.set(1500+this.random()*1e3,650+this.random()*1100,-5700-this.random()*900).multiplyScalar(Zn),this.stars.rotation.set(this.random()*Math.PI,this.random()*Math.PI,0),this.placeAsteroids(this.asteroids)}update(e){if(this.disposed||(e=Number.isFinite(e)?Math.max(0,e):0,this.elapsed+=e,this.camera.getWorldPosition(this.sky.position),this.stars.position.copy(this.sky.position),this.planet.rotation.y+=e*.002,this.moon.rotation.y+=e*.003,this.warpState==="idle"))return;this.warpTimer+=e;let t=0;if(this.warpState==="charging")t=Math.min(.3,this.warpTimer/1.1*.3),this.warpTimer>=1.1&&(this.warpState="jumping",this.warpTimer=0);else if(this.warpState==="jumping"){if(t=Math.min(1,.3+this.warpTimer*.5),this.warpTimer>=2.4){this.warpState="arriving",this.warpTimer=0,this.reroll();const n=this.onArrive;this.onArrive=null,n?.()}}else t=Math.max(0,1-this.warpTimer/1.1),this.warpTimer>=1.1&&(this.warpState="idle",t=0,this.warpOverlay.visible=!1);this.warpMaterial.uniforms.uWarp.value=t,this.warpMaterial.uniforms.uTime.value=this.elapsed,this.warpMaterial.uniforms.uAspect.value=this.camera.aspect}dispose(){this.disposed||(this.disposed=!0,this.onArrive=null,this.warpState="idle",this.camera.remove(this.warpOverlay),this.root.add(this.warpOverlay),this.scene.remove(this.root),ru(this.root),this.sunLight.dispose(),this.ambient.dispose(),this.root.clear())}}const ax={standby:!1,power_state:"unknown",power_available:!1,reason:null,operator:null,since_text:null,standby_seconds:null,online:!1,plugins:{total:0,running:0,error:0},uptime_seconds:0};class lx{status={...ax};manageEnabled=!0;playerName="舰长";quality="medium";listeners=new Set;subscribe(e){return this.listeners.add(e),()=>this.listeners.delete(e)}update(e){this.status={...this.status,...e},this.emit()}setManageEnabled(e){this.manageEnabled!==e&&(this.manageEnabled=e,this.emit())}emit(){for(const e of this.listeners)e()}availability(e){const t={usage:{reason:"待机中：模型调用统计已停止采集",hint:"在主控台点击「恢复运行」后重新上线"},analysis:{reason:"待机中：Agent 运行时未启动",hint:"在主控台点击「恢复运行」后重新上线"},bots:{reason:"待机中：OneBot 连接已断开",hint:"在主控台点击「恢复运行」后重新上线"}};if(this.status.standby){const n=t[e];return n?{available:!1,reason:n.reason,hint:n.hint,readOnly:!0}:{available:!0,reason:"舰船处于低功耗待机状态",hint:"",readOnly:!1}}return e==="bots"&&!this.status.online?{available:!0,reason:"未检测到 OneBot 连接：数据可能不是最新的",hint:"确认 NapCat / OneBot 是否已启动",readOnly:!1}:(e==="plugins"||e==="config")&&!this.manageEnabled?{available:!0,reason:"当前会话为只读模式（manage_plugins=false 或远程管理已关闭）",hint:"在面板「配置管理 → dashboard」中开启管理功能",readOnly:!0}:{available:!0,reason:"",hint:"",readOnly:!1}}}class cx{element;active=!1;composing=!1;value="";onCommit=null;onCancel=null;onType=null;constructor(){const e=document.createElement("input");e.type="text",e.autocomplete="off",e.autocapitalize="off",e.spellcheck=!1,e.setAttribute("aria-hidden","true"),e.className="text-capture",document.body.appendChild(e),this.element=e,e.addEventListener("input",()=>{this.value=e.value,this.onType?.(this.value)}),e.addEventListener("compositionstart",()=>{this.composing=!0}),e.addEventListener("compositionend",()=>{this.composing=!1,this.value=e.value,this.onType?.(this.value)}),e.addEventListener("keydown",t=>{if(this.active&&(t.stopPropagation(),!(this.composing||t.isComposing||t.keyCode===229))){if(t.key==="Enter"){t.preventDefault();const n=e.value,i=this.onCommit;this.close(),i?.(n)}else if(t.key==="Escape"){t.preventDefault();const n=this.onCancel;this.close(),n?.()}}}),e.addEventListener("blur",()=>{if(this.active){const t=this.onCancel;this.close(),t?.()}})}get isActive(){return this.active}open(e){this.value=e.initial??"",this.element.value=this.value,this.onCommit=e.onCommit,this.onCancel=e.onCancel??null,this.onType=e.onType??null,this.composing=!1,this.active=!0,this.element.focus({preventScroll:!0}),this.element.setSelectionRange(this.value.length,this.value.length)}dispose(){this.close(),this.element.remove()}close(){this.active=!1,this.composing=!1,this.onCommit=null,this.onCancel=null,this.onType=null,this.element.blur()}}function Fs(s){switch(s){case"navigation":return{kind:"chart-basin",center:[0,1.48,.94],tilt:-.48,width:2.48,height:1.12,columns:3};case"system":return{kind:"power-prism",center:[0,1.66,.73],tilt:-.16,width:2.12,height:1.82,columns:2};case"bots":return{kind:"communications-wings",center:[0,1.62,.84],tilt:-.22,width:2.48,height:1.82,columns:2};case"plugins":return{kind:"module-slots",center:[0,1.52,.86],tilt:-.28,width:2.48,height:1.12,columns:3};case"usage":return{kind:"telemetry-dial",center:[0,1.58,.91],tilt:-.32,width:2.48,height:1.12,columns:3};case"dashboard":return{kind:"command-crown",center:[0,1.55,.87],tilt:-.28,width:2.48,height:1.12,columns:3};default:return{kind:s==="logs"?"archive-book":"foldout-projector",center:[0,1.84,.64],tilt:-.12,width:2.5,height:2.5*576/1024,columns:0}}}function ou(s,e){s.position.set(...e.center),s.rotation.x=e.tilt}function Qc(s,e,t,n){s.updateWorldMatrix(!0,!1);const i=s.getWorldPosition(new w),r=new w(0,0,1).transformDirection(s.matrixWorld),o=s.getWorldScale(new w),a=Math.tan(_t.degToRad(n.fov/2)),l=Math.max(e*o.x/(2*a*Math.max(.4,n.aspect)*.86),t*o.y/(2*a*.84));return{target:i,position:i.clone().addScaledVector(r,l)}}class hx{constructor(e,t=2.5,n=1.40625,i="config"){if(this.stationId=i,i!=="navigation"){this.buildInstrument(t,n);return}this.group.name="khalai-segmented-star-basin";const r=new Map,o=(T,y,b=[0,0,0],D=[0,0,0],L=[1,1,1])=>{const N=T.index?T.toNonIndexed():T.clone();T.dispose(),N.deleteAttribute("uv"),N.applyMatrix4(new Fe().compose(new w(...b),new Pt().setFromEuler(new Yt(...D)),new w(...L)));const B=r.get(y)??[];B.push(N),r.set(y,B)},a=(T,y=0,b=Math.PI*2)=>new jr(T.map(([D,L])=>new Q(D,L)),Math.max(8,Math.ceil(b*18)),y,b),l=[[1.06,.22],[1.29,.28],[1.4,.46],[1.41,.71],[1.32,.94],[1.22,1.02],[.88,.98],[.8,.89],[.84,.75],[1.05,.68],[1.06,.22]];o(new et(1.31,1.44,.14,64),this.obsidian,[0,.1,0]),o(a([[1.27,.15],[1.36,.19],[1.31,.26],[1.27,.15]]),this.edge),o(a(l),this.obsidian,[0,-.008,0],[0,0,0],[.994,1,.994]);for(let T=0;T<12;T++){const y=T*Math.PI/6+.024;o(a(l,y,Math.PI/6-.048),T%3===0?this.edge:this.gold),o(a([[1.405,.48],[1.435,.51],[1.435,.66],[1.403,.72],[1.405,.48]],y+.035,Math.PI/6-.118),this.ceramic),o(a([[1.29,.975],[1.265,.994],[1.01,1.008],[1,.998],[1.29,.975]],y+.07,Math.PI/6-.18),this.ceramic);for(const D of[.38,.42])o(a([[1.365,D],[1.38,D+.013],[1.39,D+.026]],y+.055,Math.PI/6-.16),this.obsidian);const b=y+.24;o(new ft(.045,8,6),this.light,[Math.sin(b)*1.414,.585,Math.cos(b)*1.414],[0,b,0],[.65,1.5,.45])}o(a([[.69,.69],[.79,.74],[.86,.88],[.84,.93],[.79,.94],[.74,.82],[.69,.69]]),this.ceramic),o(new et(.77,.77,.045,64),this.obsidian,[0,.77,0]),o(new et(.73,.73,.013,64),this.projection,[0,.8,0]);for(const T of[.36,.62,.77])o(new at(T,.009,4,64),this.light,[0,.816,0],[Math.PI/2,0,0]);const c=new De;c.moveTo(.99,.3),c.bezierCurveTo(1.45,.41,1.5,.92,1.41,1.47),c.bezierCurveTo(1.3,1.18,1.21,1.02,1.13,.95),c.bezierCurveTo(1.05,.77,1.22,.56,.99,.3),c.closePath();const h=(T,y,b=.025)=>{const D=new xt(T,{depth:y,bevelEnabled:!0,bevelThickness:b,bevelSize:b,bevelSegments:2,curveSegments:12,steps:1});return D.translate(0,0,-y/2),D},u=(T,y,b,D,L)=>{const N=h(T,D,L),B=N.getAttribute("position");let k=Array.from(B.array);for(let U=0;U<1;U++){const V=[];for(let P=0;P<k.length;P+=9){const O=k.slice(P,P+3),H=k.slice(P+3,P+6),Z=k.slice(P+6,P+9),W=O.map((he,Ce)=>(he+H[Ce])/2),$=H.map((he,Ce)=>(he+Z[Ce])/2),le=Z.map((he,Ce)=>(he+O[Ce])/2);V.push(...O,...W,...le,...W,...H,...$,...le,...$,...Z,...W,...$,...le)}k=V}N.dispose();for(let U=0;U<k.length;U+=3){const V=y+k[U]/1.44,P=k[U+1],O=1.415+Math.sin((P-.22)/.74*Math.PI)*.035+b+k[U+2];k[U]=Math.sin(V)*O,k[U+2]=Math.cos(V)*O}const q=new je;return q.setAttribute("position",new Ae(k,3)),q.computeVertexNormals(),q},d=new De;d.moveTo(-.55,.65),d.lineTo(-.43,.87),d.lineTo(-.11,.91),d.lineTo(.42,.82),d.lineTo(.55,.61),d.lineTo(.37,.34),d.lineTo(.02,.265),d.lineTo(-.39,.35),d.closePath();const f=new De;f.moveTo(-.38,.59),f.lineTo(-.28,.735),f.lineTo(.12,.765),f.lineTo(.35,.64),f.lineTo(.23,.46),f.lineTo(-.08,.42),f.lineTo(-.29,.46),f.closePath();const g=new De;g.moveTo(-.34,.55),g.lineTo(-.17,.6),g.lineTo(.25,.7),g.lineTo(.05,.56),g.lineTo(-.12,.52),g.lineTo(-.28,.49),g.closePath();for(let T=0;T<6;T++){const y=T*Math.PI/3+Math.PI/6;o(u(d,y,.018,.05,.018),this.obsidian),o(u(d,y,.042,.035,.011),this.plate),o(u(f,y,.065,.016,.012),this.edge),o(u(f,y,.077,.008,.001),this.enamel),o(u(g,y,.085,.012,.004),this.obsidian);const b=new De;b.moveTo(-.33,.79),b.lineTo(-.08,.845),b.lineTo(.3,.78),b.lineTo(.29,.766),b.lineTo(-.07,.829),b.lineTo(-.34,.775),b.closePath(),o(u(b,y,.065,.006,.002),this.obsidian)}for(const T of[-1,1])o(h(c,.18),this.gold,[0,0,-.34],[0,T===1?0:Math.PI,0]),o(h(c,.195,.01),this.ceramic,[T*.08,.1,-.34],[0,T===1?0:Math.PI,0],[.89,.81,1]);const x=new De;x.moveTo(0,.84),x.bezierCurveTo(.12,.63,.29,.62,.32,.47),x.lineTo(.19,.3),x.lineTo(0,.12),x.lineTo(-.19,.3),x.lineTo(-.32,.47),x.bezierCurveTo(-.29,.62,-.12,.63,0,.84),x.closePath(),o(h(x,.11),this.edge,[0,0,1.36]),o(h(x,.025,.008),this.obsidian,[0,.065,1.434],[0,0,0],[.77,.77,1]),o(h(x,.03,.008),this.gold,[0,.12,1.45],[0,0,0],[.5,.6,1]);const p=new De;p.moveTo(0,.855),p.lineTo(.063,.63),p.lineTo(.045,.49),p.lineTo(.095,.38),p.lineTo(0,.14),p.lineTo(-.095,.38),p.lineTo(-.045,.49),p.lineTo(-.063,.63),p.closePath(),o(h(p,.04,.013),this.plate,[0,0,1.491]);const m=new De;m.moveTo(0,.81),m.lineTo(.012,.61),m.lineTo(.01,.38),m.lineTo(0,.2),m.lineTo(-.01,.38),m.lineTo(-.012,.61),m.closePath(),o(h(m,.007,.001),this.obsidian,[0,0,1.526]);for(const T of[-1,1]){const y=new De;y.moveTo(T*.05,.63),y.lineTo(T*.18,.55),y.lineTo(T*.29,.48),y.lineTo(T*.2,.4),y.lineTo(T*.13,.26),y.lineTo(T*.16,.46),y.lineTo(T*.11,.5),y.closePath(),o(h(y,.018,.009),this.edge,[0,0,1.485]);const b=new De;b.moveTo(T*.08,.57),b.lineTo(T*.135,.52),b.lineTo(T*.115,.4),b.lineTo(T*.065,.46),b.closePath(),o(h(b,.02,.006),this.enamel,[0,0,1.5])}o(new ft(.038,8,6),this.light,[0,.45,1.551],[0,0,0],[.65,1.65,.45]);for(const[T,y]of r){const b=cs(y,!1);if(y.forEach(L=>L.dispose()),!b)throw new Error("Console geometry batching failed");const D=this.addMesh(this.group,b,T);D.name="basin-armor",D.scale.set(.91,1,.91)}this.panel.position.set(0,1.015,1.025),this.panel.rotation.x=-1.02,this.group.add(this.panel),this.addMesh(this.panel,new lt(t+.13,n+.12,.07),this.gold);const _=this.addMesh(this.panel,new lt(t+.025,n+.025,.035),this.obsidian);_.position.z=.048,["scroll-up","refresh","scroll-down"].forEach((T,y)=>{const b=this.addMesh(this.panel,new et(.066,.079,.05,6),this.edge);b.rotation.x=Math.PI/2,b.position.set((y-1)*.25,-n/2-.055,.07),b.name="console-key-"+T,b.userData.consoleKey=T,this.keys.push(b);const D=y===1?new at(.026,.006,4,14,Math.PI*1.7):new rs(.03,3),L=this.addMesh(this.panel,D,this.light);L.position.copy(b.position),L.position.z+=.033,y!==1&&(L.rotation.z=y===0?Math.PI/2:-Math.PI/2)}),this.core.position.set(0,1.43,-.12),this.group.add(this.core),this.addMesh(this.core,new ft(.29,28,16),this.projection);const M=new ft(.3,12,8),S=new y1(M);M.dispose(),this.geometries.add(S);const E=new Hg(S,this.gridMaterial);this.core.add(E),this.gimbal.position.copy(this.core.position),this.group.add(this.gimbal);for(let T=0;T<3;T++){const y=this.addMesh(this.gimbal,new at(.43+T*.12,.006,4,64),this.light);y.rotation.set(.9+T*.43,T*.7,T*.55);const b=this.addMesh(y,new ft(.032+T*.006,10,8),this.light);b.position.x=.43+T*.12}const C=[];for(let T=0;T<90;T++){const y=T*2.399963,b=.12+Math.sqrt(T/90)*.57;C.push(Math.sin(y)*b,Math.sin(T*1.7)*.12-.24,Math.cos(y)*b)}const z=new je;z.setAttribute("position",new Ae(C,3)),this.geometries.add(z),this.core.add(new ol(z,this.particleMaterial))}group=new qe;panel=new qe;keys=[];core=new qe;gimbal=new qe;gold=new Ke({color:8549458,metalness:.72,roughness:.48});edge=new Ke({color:11837562,metalness:.7,roughness:.4});plate=new Ke({color:10586969,metalness:.6,roughness:.46,emissive:2431239,emissiveIntensity:.09});enamel=new Ke({color:3560284,metalness:.38,roughness:.4});obsidian=new Ke({color:529174,metalness:.55,roughness:.38});ceramic=new Ke({color:1456960,metalness:.36,roughness:.4});light=new Ge({color:2592232,toneMapped:!1});projection=new Ge({color:2194899,transparent:!0,opacity:.38,depthWrite:!1,blending:Mn,toneMapped:!1});gridMaterial=new sl({color:4761309,transparent:!0,opacity:.4,depthWrite:!1});geometries=new Set;particleMaterial=new rl({color:6539775,size:.025,transparent:!0,opacity:.75,depthWrite:!1,blending:Mn});time=0;disposed=!1;buildInstrument(e,t){const n=this.stationId,i=Fs(n);this.group.name="khalai-"+i.kind;const r=(l,c,h,u,d)=>{const f=this.addMesh(this.group,l,c);return f.position.set(h,u,d),f},o=(l,c,h,u,d,f,g=this.gold)=>r(new lt(l,c,h),g,u,d,f),a=r(new et(.7,.94,.18,6),this.obsidian,0,.12,-.12);if(a.rotation.y=Math.PI/6,o(.45,.7,.48,0,.52,-.16,this.ceramic),n==="system"){r(new qt(.72),this.enamel,0,1.58,-.32).scale.set(.7,1.78,.65);for(const c of[-1,1]){const h=o(.19,1.8,.3,c*.58,1.46,-.38);h.rotation.z=c*-.16,o(.045,1.4,.03,c*.57,1.55,-.18,this.light)}for(let c=0;c<5;c++)o(.68,.065,.5,0,.92+c*.23,-.15,this.edge)}else if(n==="bots"){for(const l of[-1,1]){const c=new De;c.moveTo(.16,.7),c.lineTo(.6,1),c.lineTo(1.35,2.35),c.lineTo(1.3,1.25),c.lineTo(.98,.67),c.closePath();const h=new xt(c,{depth:.2,bevelEnabled:!1}),u=r(h,this.gold,0,0,-.35);u.scale.x=l;const d=o(.06,.76,.055,l*1.15,1.86,-.08,this.light);d.rotation.z=l*-.3;for(let f=0;f<3;f++)o(.64,.11,.22,l*.7,.86+f*.24,-.1,this.ceramic)}r(new ft(.24,16,10),this.projection,0,1.56,-.17)}else if(n==="plugins"){o(2.65,.16,.78,0,.83,-.02);for(let l=0;l<3;l++){const c=(l-1)*.83;o(.71,.76,.58,c,1.29,-.3,this.obsidian),o(.56,.65,.36,c,1.29,-.05,this.enamel),o(.44,.055,.045,c,1.57,.15,this.light);for(const h of[-1,1])o(.06,.72,.5,c+h*.32,1.29,-.02,this.edge)}}else if(n==="usage"){const l=r(new at(1.13,.12,8,64),this.gold,0,1.52,-.18);l.rotation.x=-.22;const c=r(new at(.96,.025,6,64),this.light,0,1.52,-.12);c.rotation.x=-.22;for(let h=0;h<16;h++){const u=h*Math.PI/8,d=o(.045,.16,.08,Math.sin(u)*1.1,1.52+Math.cos(u)*1.1,-.08,this.edge);d.rotation.z=-u}}else if(n==="dashboard"){o(1.8,.18,.9,0,.86,-.04);for(const c of[-1,1]){const h=r(new Kr(.23,1.4,4),this.gold,c*.91,1.49,-.3);h.rotation.z=c*-.34}const l=r(new qt(.42),this.projection,0,1.6,-.35);l.scale.y=1.4}else{o(1.62,.13,.72,0,.89,-.03);for(const l of[-1,1]){const c=o(.14,.85,.23,l*.86,1.03,-.18,this.edge);c.rotation.z=l*-.44}if(n==="logs"){for(const l of[-1,1]){const c=o(1.22,1.48,.09,l*.64,1.8,.12,this.gold);c.rotation.y=l*-.13;for(let h=0;h<4;h++)o(.025,1.38,.1,l*(1.25+h*.032),1.8,.22,this.edge)}o(.14,1.55,.13,0,1.8,.1,this.ceramic)}else for(const l of[-1,1])o(.09,1.42,.17,l*1.32,1.78,.22,this.gold),o(.027,1.3,.03,l*1.26,1.78,.34,this.light)}if(ou(this.panel,i),this.group.add(this.panel),i.columns===0){for(const c of[-1,1])this.addMesh(this.panel,new lt(e+.06,.025,.025),this.light).position.set(0,c*(t/2+.022),.01);["scroll-up","refresh","scroll-down"].forEach((c,h)=>{const u=this.addMesh(this.panel,new lt(.16,.075,.04),this.edge);u.position.set((h-1)*.24,-t/2-.095,.07),u.name="console-key-"+c,u.userData.consoleKey=c,this.keys.push(u);const d=this.addMesh(u,h===1?new at(.023,.004,4,20,Math.PI*1.7):new rs(.025,3),this.light);d.name="utility-key-glyph",d.position.z=.023,h!==1&&(d.rotation.z=h===0?Math.PI/2:-Math.PI/2)})}}setFocused(e){this.projection.opacity=e?.22:.3}addMesh(e,t,n){this.geometries.add(t);const i=new ve(t,n);return i.userData.solidConsole=n instanceof Ke&&!n.transparent,e.add(i),i}setBusinessControls(e){this.panel.visible=!e}setAccent(e){this.light.color.setHex(e===16754237?e:2592232)}update(e,t){this.time+=Math.min(Math.max(e,0),.1),this.core.position.y=1.43+Math.sin(this.time*.85)*.025,this.core.rotation.y=this.time*.055,this.gimbal.rotation.y=this.time*.08,this.projection.opacity=t?.46:.3}pressKey(e){for(const t of this.keys)t.position.z=t===e?.05:.07}dispose(){if(!this.disposed){this.disposed=!0,this.geometries.forEach(e=>e.dispose());for(const e of[this.gold,this.edge,this.plate,this.enamel,this.obsidian,this.ceramic,this.light,this.projection,this.particleMaterial,this.gridMaterial])e.dispose()}}}class ux{group=new qe;mesh;canvas;texture;radius;height;width;thetaStart;thetaLength;model;material;disposed=!1;businessTargets=null;constructor(e){this.canvas=document.createElement("canvas"),this.canvas.width=e.canvasWidth??1024,this.canvas.height=e.canvasHeight??576,this.texture=new ss(this.canvas),this.texture.colorSpace=Ft,this.texture.generateMipmaps=!1,this.texture.minFilter=Ct,this.texture.magFilter=Ct,this.radius=e.radius??1.25;const t=Fs(e.stationId??"config");this.height=e.screenHeight??t.height,this.width=this.height*this.canvas.width/this.canvas.height,this.thetaLength=e.thetaLength??0,this.thetaStart=Math.PI-this.thetaLength/2,this.material=new Ge({map:this.texture,color:8165022,side:wn,toneMapped:!1}),this.mesh=new ve(new Gt(this.width,this.height),this.material),this.mesh.name="console-inset-interface",this.model=e.withPedestal===!1?null:new hx(e.accent,this.width,this.height,e.stationId),this.model?(this.group.add(this.model.group),this.model.panel.add(this.mesh),this.mesh.position.z=.096):this.group.add(this.mesh);const n=this.mesh.raycast.bind(this.mesh);this.mesh.raycast=(i,r)=>{if(!this.disposed){this.group.updateWorldMatrix(!0,!0),this.businessTargets||n(i,r);for(const o of this.businessTargets??this.model?.keys??[]){const a=[];o.raycast(i,a);for(const l of a)delete l.uv,r.push(l)}}}}setBusinessControls(e,t){this.businessTargets=t,this.mesh.visible=!1,this.model?.setBusinessControls(!0),this.group.add(e)}setAccent(e){this.model?.setAccent(e)}setFocused(e){this.material.color.setHex(e?16777215:8165022),this.model?.setFocused(e)}update(e,t){this.model?.update(e,t)}pressKey(e){this.model?.pressKey(e)}worldCenter(e=new w){return this.mesh.updateWorldMatrix(!0,!1),this.mesh.getWorldPosition(e)}dispose(){this.disposed||(this.disposed=!0,this.model?.dispose(),this.mesh.geometry.dispose(),this.material.dispose(),this.texture.dispose())}}function dx(s,e){const t=new qe;t.name=e.title;const n=new ux({accent:e.accent,stationId:e.stationId,canvasWidth:1024,canvasHeight:576});return t.add(n.group),{group:t,screen:n}}function fx(s){return{accent:s,accentDim:On(s,.35),text:"#e6f4ff",textDim:"#8fb0c8",ok:"#4fe0a0",warn:"#ffc861",error:"#ff7b7b",panel:"rgba(10, 16, 32, 0.86)",panelEdge:"rgba(195, 161, 86, 0.65)",grid:"rgba(80, 180, 220, 0.08)"}}function On(s,e){const t=s.replace("#",""),n=parseInt(t.slice(0,2),16),i=parseInt(t.slice(2,4),16),r=parseInt(t.slice(4,6),16);return"rgba("+n+","+i+","+r+","+e+")"}const Ms='"Microsoft YaHei", "PingFang SC", "Segoe UI", system-ui, sans-serif',eh='"JetBrains Mono", "Cascadia Mono", Consolas, monospace';class px{canvas;ctx;theme;cursor={x:0,y:0,inside:!1,down:!1};hoverId=null;hits=[];previousHits=[];scroll=new Map;time=0;width;height;constructor(e,t,n,i){this.width=e,this.height=t,this.canvas=i??document.createElement("canvas"),this.canvas.width=e,this.canvas.height=t;const r=this.canvas.getContext("2d");if(!r)throw new Error("无法创建 2D 画布上下文");this.ctx=r,this.theme=fx(n)}begin(e,t,n){this.time+=e,this.previousHits=this.hits,this.hits=[];const i=this.ctx;i.save(),i.setTransform(1,0,0,1,0,0),i.clearRect(0,0,this.width,this.height);const r=i.createLinearGradient(0,0,this.width,this.height);r.addColorStop(0,"rgba(4, 14, 22, 0.96)"),r.addColorStop(.55,"rgba(6, 20, 30, 0.94)"),r.addColorStop(1,"rgba(3, 10, 18, 0.97)"),i.fillStyle=r,i.fillRect(0,0,this.width,this.height),i.strokeStyle=this.theme.grid,i.lineWidth=1;for(let o=0;o<this.width;o+=32)i.beginPath(),i.moveTo(o+.5,0),i.lineTo(o+.5,this.height),i.stroke();for(let o=0;o<this.height;o+=32)i.beginPath(),i.moveTo(0,o+.5),i.lineTo(this.width,o+.5),i.stroke();i.fillStyle="rgba(120, 220, 255, 0.025)";for(let o=0;o<this.height;o+=4)i.fillRect(0,o,this.width,1);tu(i,{x:0,y:0,w:this.width,h:64}),i.font="bold 30px "+Ms,i.fillStyle=this.theme.text,i.textAlign="left",i.textBaseline="middle",i.fillText(t,24,33),i.font="18px "+Ms,i.fillStyle=this.theme.textDim,i.textAlign="right",i.fillText(n,this.width-24,34),i.textAlign="left"}end(){const e=this.ctx;if(this.cursor.inside){const{x:r,y:o}=this.cursor;e.save(),e.strokeStyle=this.theme.accent,e.lineWidth=2,e.beginPath(),e.moveTo(r-12,o),e.lineTo(r-4,o),e.moveTo(r+4,o),e.lineTo(r+12,o),e.moveTo(r,o-12),e.lineTo(r,o-4),e.moveTo(r,o+4),e.lineTo(r,o+12),e.stroke(),e.beginPath(),e.arc(r,o,3.5,0,Math.PI*2),e.stroke(),e.restore()}e.strokeStyle=On(this.theme.accent,.8),e.lineWidth=3;const t=26,n=8,i=[[n,n,1,1],[this.width-n,n,-1,1],[n,this.height-n,1,-1],[this.width-n,this.height-n,-1,-1]];for(const[r,o,a,l]of i)e.beginPath(),e.moveTo(r+a*t,o),e.lineTo(r,o),e.lineTo(r,o+l*t),e.stroke();e.restore()}text(e,t,n,i={}){const r=this.ctx;r.font=(i.weight?i.weight+" ":"")+(i.size??18)+"px "+(i.mono?eh:Ms),r.fillStyle=i.color||this.theme.text,r.textAlign=i.align||"left",r.textBaseline=i.baseline||"alphabetic",i.maxWidth?r.fillText(n,e,t,i.maxWidth):r.fillText(n,e,t)}panel(e,t={}){const n=this.ctx;n.save(),n.fillStyle=this.theme.panel,n.fillRect(e.x,e.y,e.w,e.h),n.strokeStyle=t.tone||this.theme.panelEdge,n.lineWidth=1.5,n.strokeRect(e.x+.5,e.y+.5,e.w-1,e.h-1);const i=14;n.beginPath(),n.moveTo(e.x,e.y+i),n.lineTo(e.x+i,e.y),n.moveTo(e.x+e.w-i,e.y),n.lineTo(e.x+e.w,e.y+i),n.moveTo(e.x,e.y+e.h-i),n.lineTo(e.x+i,e.y+e.h),n.moveTo(e.x+e.w-i,e.y+e.h),n.lineTo(e.x+e.w,e.y+e.h-i),n.strokeStyle=t.tone||this.theme.accent,n.lineWidth=3,n.stroke(),t.title&&(n.fillStyle=t.tone||this.theme.accent,n.font="bold 19px "+Ms,this.text(e.x+14,e.y+24,t.title,{size:19,weight:"bold",color:t.tone||this.theme.accent}),n.fillStyle=On("#ffffff",.06),n.fillRect(e.x+1,e.y+34,e.w-2,1)),n.restore()}hit(e,t){this.hits.push({id:e,rect:t});const n=this.cursor.x>=t.x&&this.cursor.x<=t.x+t.w&&this.cursor.y>=t.y&&this.cursor.y<=t.y+t.h;return n&&(this.hoverId=e),n}isHovered(e){return this.hoverId===e}hoverRect(e,t){this.hits.push({id:e,rect:t});const n=this.cursor.x>=t.x&&this.cursor.x<=t.x+t.w&&this.cursor.y>=t.y&&this.cursor.y<=t.y+t.h;return n&&(this.hoverId=e),n}button(e,t,n,i={}){const r=this.ctx,o=this.hoverRect(e,t),a=i.tone||this.theme.accent;return r.save(),fl(r,t,{hovered:o,pressed:o&&this.cursor.down,disabled:i.disabled,danger:a===this.theme.error||a===this.theme.warn}),r.font="bold "+(i.size??18)+"px "+Ms,r.fillStyle=i.disabled?"#a8b7c4":this.theme.text,r.textAlign="center",r.textBaseline="middle",r.fillText(n,t.x+t.w/2,t.y+t.h/2+1,t.w-12),r.restore(),i.disabled?!1:o&&this.clicked}clicked=!1;toggle(e,t,n,i){const r=this.ctx,o=this.hoverRect(e,t);r.save(),r.fillStyle=o?"rgba(40,60,80,0.6)":"rgba(20,32,44,0.55)",r.fillRect(t.x,t.y,t.w,t.h),r.strokeStyle=i?this.theme.ok:this.theme.textDim,r.lineWidth=1.5,r.strokeRect(t.x+.5,t.y+.5,t.w-1,t.h-1);const a=46,l=t.x+t.w-a-14,c=t.y+t.h/2-6;return r.fillStyle=i?On(this.theme.ok,.35):"rgba(90,100,110,0.45)",r.fillRect(l,c,a,12),r.fillStyle=i?this.theme.ok:"#8a949e",r.fillRect(i?l+a-12:l,c-3,12,18),this.text(t.x+12,t.y+t.h/2+6,n,{size:17}),r.restore(),o&&this.clicked}progress(e,t,n={}){const i=this.ctx,r=n.color||this.theme.accent,o=Math.max(0,Math.min(1,t));i.save(),i.fillStyle="rgba(16, 30, 42, 0.85)",i.fillRect(e.x,e.y,e.w,e.h);const a=i.createLinearGradient(e.x,0,e.x+e.w,0);a.addColorStop(0,On(r,.55)),a.addColorStop(1,r),i.fillStyle=a,i.fillRect(e.x,e.y,e.w*o,e.h),i.strokeStyle=On(r,.7),i.lineWidth=1,i.strokeRect(e.x+.5,e.y+.5,e.w-1,e.h-1),n.label&&this.text(e.x,e.y-6,n.label,{size:15,color:this.theme.textDim}),n.showValue!==!1&&this.text(e.x+e.w-8,e.y+e.h/2+6,(o*100).toFixed(0)+"%"+(n.suffix||""),{size:15,align:"right",color:this.theme.text}),i.restore()}sparkline(e,t,n={}){const i=this.ctx,r=n.color||this.theme.accent;if(i.save(),i.fillStyle="rgba(10, 22, 32, 0.6)",i.fillRect(e.x,e.y,e.w,e.h),t.length>1){const o=Math.max(...t,1),a=Math.min(...t,0),l=Math.max(o-a,1);i.beginPath(),t.forEach((c,h)=>{const u=e.x+h/(t.length-1)*e.w,d=e.y+e.h-(c-a)/l*(e.h-12)-6;h===0?i.moveTo(u,d):i.lineTo(u,d)}),i.strokeStyle=r,i.lineWidth=2,i.stroke(),n.fill&&(i.lineTo(e.x+e.w,e.y+e.h),i.lineTo(e.x,e.y+e.h),i.closePath(),i.fillStyle=On(r,.16),i.fill())}i.strokeStyle=On(r,.5),i.lineWidth=1,i.strokeRect(e.x+.5,e.y+.5,e.w-1,e.h-1),n.label&&this.text(e.x+8,e.y+20,n.label,{size:15,color:this.theme.textDim}),n.valueText&&this.text(e.x+e.w-8,e.y+20,n.valueText,{size:16,align:"right",color:this.theme.text}),i.restore()}bars(e,t,n={}){const i=this.ctx,r=n.max??Math.max(...t.map(a=>a.value),1),o=Math.min(26,(e.h-8)/Math.max(t.length,1)-6);i.save(),t.forEach((a,l)=>{const c=e.y+l*(o+6),h=120,u=e.w-h-70;this.text(e.x,c+o-6,a.label,{size:15,color:this.theme.textDim,maxWidth:h-8}),i.fillStyle="rgba(20, 36, 50, 0.8)",i.fillRect(e.x+h,c,u,o);const d=Math.max(0,Math.min(1,a.value/r));i.fillStyle=a.color||this.theme.accent,i.fillRect(e.x+h,c,u*d,o),this.text(e.x+e.w,c+o-6,String(a.value),{size:15,align:"right",color:this.theme.text})}),i.restore()}list(e,t,n,i={}){const r=this.ctx,o=i.rowHeight??44,a=i.scrollable===!1?0:this.scroll.get(e)??0,l=Math.floor(t.h/o),c=Math.max(0,n.length-l),h=Math.max(0,Math.min(c,Math.round(a)));this.scroll.set(e,h),r.save(),r.beginPath(),r.rect(t.x,t.y,t.w,t.h),r.clip(),r.fillStyle="rgba(8, 20, 30, 0.5)",r.fillRect(t.x,t.y,t.w,t.h);let u=-1;for(let d=h;d<Math.min(n.length,h+l+1);d+=1){const f=n[d],g=t.y+(d-h)*o,x={x:t.x,y:g,w:t.w-(c>0?10:0),h:o-2},p=this.hoverRect(e+":"+d,x);p&&this.clicked&&(u=d),r.fillStyle=p?"rgba(60, 120, 160, 0.35)":f.active?"rgba(40, 90, 120, 0.35)":d%2===0?"rgba(12, 26, 38, 0.45)":"rgba(10, 22, 32, 0.35)",r.fillRect(x.x,x.y,x.w,x.h),f.tone&&(r.fillStyle=f.tone,r.fillRect(t.x,g,3,o-2)),this.text(t.x+14,g+(f.sub?19:o/2+4),f.label,{size:17,maxWidth:t.w-140}),f.sub&&this.text(t.x+14,g+36,f.sub,{size:14,color:this.theme.textDim,maxWidth:t.w-140}),f.badge&&this.text(t.x+t.w-20,g+o/2+4,f.badge,{size:14,align:"right",color:this.theme.textDim})}if(r.restore(),c>0){const d=t.h,f=Math.max(28,l/n.length*d),g=t.y+h/c*(d-f);r.fillStyle="rgba(80, 140, 180, 0.35)",r.fillRect(t.x+t.w-6,g,5,f)}return u}keyValue(e,t,n,i,r,o){this.text(e,t,i,{size:16,color:this.theme.textDim}),this.text(e+n,t,r,{size:17,align:"right",color:o||this.theme.text})}textField(e,t,n,i={}){const r=this.ctx,o=this.hoverRect(e,t),a=o&&this.clicked;r.save(),r.fillStyle=i.focused?"rgba(20, 50, 70, 0.85)":"rgba(14, 28, 40, 0.75)",r.fillRect(t.x,t.y,t.w,t.h),r.strokeStyle=i.focused?this.theme.accent:On(this.theme.accent,.4),r.lineWidth=i.focused?2:1,r.strokeRect(t.x+.5,t.y+.5,t.w-1,t.h-1),r.beginPath(),r.rect(t.x+6,t.y+4,t.w-12,t.h-8),r.clip();const l=n||i.placeholder||"";if(r.font=(i.multiline?"16px ":"17px ")+eh,r.fillStyle=n?this.theme.text:this.theme.textDim,(i.multiline?l.split(`
`).slice(0,Math.floor(t.h/20)):[l]).forEach((h,u)=>{r.fillText(h,t.x+10,t.y+24+u*20)}),i.focused&&Math.floor(this.time*2)%2===0){const h=i.caret??n.length,u=n.slice(0,h),d=r.measureText(u).width;r.fillStyle=this.theme.accent,r.fillRect(t.x+10+d+1,t.y+8,2,t.h-16)}return r.restore(),{clicked:a,hovered:o}}gauge(e,t,n,i={}){const r=this.ctx,o=i.color||this.theme.accent,a=Math.max(0,Math.min(1,n));r.save(),r.lineWidth=10,r.strokeStyle="rgba(30, 50, 66, 0.9)",r.beginPath(),r.arc(e.x,e.y,t,Math.PI*.75,Math.PI*.25+Math.PI*2*.999),r.stroke(),r.strokeStyle=o,r.beginPath(),r.arc(e.x,e.y,t,Math.PI*.75,Math.PI*.75+a*Math.PI*1.5),r.stroke(),r.fillStyle=o;for(let l=0;l<=24;l+=1){const c=Math.PI*.75+l/24*Math.PI*1.5,h=t-16,u=t-11;r.globalAlpha=l/24<=a?1:.25,r.beginPath(),r.moveTo(e.x+Math.cos(c)*h,e.y+Math.sin(c)*h),r.lineTo(e.x+Math.cos(c)*u,e.y+Math.sin(c)*u),r.lineWidth=2,r.strokeStyle=o,r.stroke()}r.globalAlpha=1,i.valueText&&this.text(e.x,e.y+8,i.valueText,{size:26,align:"center",color:this.theme.text,weight:"bold"}),i.label&&this.text(e.x,e.y+t-6,i.label,{size:15,align:"center",color:this.theme.textDim}),r.restore()}scrollBy(e,t){const n=this.scroll.get(e)??0;this.scroll.set(e,n+t)}scrollReset(e){this.scroll.set(e,0)}hitTest(e,t){for(let n=this.previousHits.length-1;n>=0;n-=1){const i=this.previousHits[n];if(e>=i.rect.x&&e<=i.rect.x+i.rect.w&&t>=i.rect.y&&t<=i.rect.y+i.rect.h)return i.id}return null}}function Ps(s,e=2){return String(s).padStart(e,"0")}function ni(s){if(s==null||!Number.isFinite(s)||s<=0)return"—";const e=Math.floor(s),t=Math.floor(e/86400),n=Math.floor(e%86400/3600),i=Math.floor(e%3600/60),r=e%60;return t>0?t+" 天 "+n+" 小时":n>0?n+" 小时 "+Ps(i)+" 分":i>0?i+" 分 "+Ps(r)+" 秒":r+" 秒"}function vt(s){return s==null||!Number.isFinite(s)?"—":Math.round(s).toLocaleString("zh-CN")}function Zi(s){return s==null||!Number.isFinite(s)?"—":s>=1e6?(s/1e6).toFixed(2)+"M":s>=1e3?(s/1e3).toFixed(1)+"K":String(Math.round(s))}function Rs(s){return s==null||!Number.isFinite(s)?"—":s===0?"¥0":s<.01?"¥"+s.toFixed(4):s<1?"¥"+s.toFixed(3):"¥"+s.toFixed(2)}function mx(s){if(!s)return"—";const e=new Date(s);return Number.isNaN(e.getTime())?String(s).slice(11,19)||"—":Ps(e.getHours())+":"+Ps(e.getMinutes())+":"+Ps(e.getSeconds())}function Hr(s){return s.status===401?"面板会话已失效，请回到控制台重新登录":s.error||"请求失败"}const gx=new Set(["navigation","dashboard","system","usage","bots","plugins"]),vx=["天鹅座 λ-4","猎户悬臂 K-17","南门二 β","天苑四 ε","蛇夫座 9","武仙座 τ","船底座 HD-7","仙女座 M31-附","半人马 ζ","天琴座 Vega-2"];function xx(s,e,t){return gx.has(s)?new _x(s,e,t):null}class _x{constructor(e,t,n){this.id=e,this.ctx=t,this.accent=n,this.group.name="physical-business-"+e,this.atlas.width=2048,this.atlas.height=1024,this.texture=new ss(this.atlas),this.texture.colorSpace=Ft,this.texture.generateMipmaps=!1,this.texture.minFilter=Ct;const i=this.labelMaterial=new Ge({map:this.texture,transparent:!0,depthWrite:!0,alphaTest:.02,toneMapped:!1}),r=new Ge({color:16777215,toneMapped:!1});[this.gold,this.dark,this.warning,this.touch,this.hologram,this.holoDisabled,this.holoWarning,this.runes,i,r].forEach(x=>this.materials.add(x));const o=Fs(e);ou(this.operatingSurface,o),this.group.add(this.operatingSurface);const a=(x,p,m,_,v)=>{const M=new Gt(p,m),S=M.getAttribute("uv");for(let C=0;C<S.count;C++)S.setY(C,(7-x+S.getY(C))/8);this.geometry.add(M);const E=new ve(M,i);return E.name=x<6?"action-label":"business-readout-"+x,E.userData.readout=x>=6,E.position.set(_,v,.035),this.operatingSurface.add(E),E},l=o.columns,c=6/l,h=l===2?e==="bots"?.92:.94:.76,u=.245;for(let x=0;x<6;x++){const p=(x%l-(l-1)/2)*(o.width/l),m=.12-Math.floor(x/l)*.31,_=a(x,h,u,p,m);_.name=e+"-business-key-"+x,_.userData.physicalAction=x,_.userData.projected=e==="navigation"||x>=3,_.userData.labelWidth=h,_.userData.labelHeight=u,this.targets.push(_);const v=new lt(h+.022,u+.018,.018);this.geometry.add(v);const M=new ve(v,_.userData.projected?this.hologram:this.touch);M.userData.solidConsole=!_.userData.projected,M.position.set(p,m,.009),this.operatingSurface.add(M)}a(6,o.width-.08,.19,0,.42),a(7,o.width-.08,.19,0,.12-c*.31);const d=new lt(.038,.022,.085);this.geometry.add(d),this.ring=new il(d,r,24);const f=new Mt;for(let x=0;x<24;x++){const p=-Math.PI*.8+x/23*Math.PI*1.6;f.position.set(Math.sin(p)*.7,.858,Math.cos(p)*.7),f.rotation.y=p,f.updateMatrix(),this.ring.setMatrixAt(x,f.matrix),this.ring.setColorAt(x,new Ne(1780274))}this.group.add(this.ring);const g=new Kr(.025,.105,4);g.rotateX(Math.PI/2),g.translate(0,0,.58),this.geometry.add(g),this.needle=new ve(g,this.gold),this.needle.position.set(0,.875,0),this.group.add(this.needle),this.configurePolling(),this.sync()}group=new qe;targets=[];operatingSurface=new qe;pollers=[];atlas=document.createElement("canvas");texture;labelMaterial;ring;needle;geometry=new Set;materials=new Set;gold=new Ke({color:8549458,metalness:.65,roughness:.44});dark=new Ke({color:1516850,metalness:.6,roughness:.45});warning=new Ke({color:10309684,emissive:4132870,metalness:.5,roughness:.3});touch=new Ke({color:2179402,emissive:1064793,emissiveIntensity:.18,metalness:.4,roughness:.44});hologram=new Ge({color:2264012,transparent:!0,opacity:.105,depthWrite:!1,side:Dt,blending:Mn,toneMapped:!1});holoDisabled=new Ge({color:2646140,transparent:!0,opacity:.035,depthWrite:!1,side:Dt});holoWarning=new Ge({color:14387025,transparent:!0,opacity:.13,depthWrite:!1,side:Dt,blending:Mn});runes=new sl({color:4893405,transparent:!0,opacity:.3,depthWrite:!1});overview=null;system=null;usage=null;plugins=null;bots=null;latency=null;power=null;tasks=null;services=null;errors=new Map;selected=0;metric=0;busy=!1;focused=!1;disposed=!1;available=!0;reason="";signature="";keys=[];hovered=null;pressed=!1;poll(e,t,n){this.pollers.push(new dt(()=>this.ctx.host.consoleApi.get(e),t,i=>{this.disposed||(this.errors.delete(e),n(i),this.ctx.redraw(),this.sync())},i=>{this.errors.set(e,i),this.ctx.redraw(),this.sync()}))}configurePolling(){this.id==="system"?(this.poll("/api/system",3e3,e=>this.system=e),this.poll("/api/tasks",15e3,e=>this.tasks=e),this.poll("/api/services",3e4,e=>this.services=e)):this.id==="usage"?this.poll("/api/stats/usage?hours=24",3e4,e=>this.usage=e):this.id==="plugins"?this.poll("/api/plugins",12e3,e=>{this.plugins=e,typeof e.manage_enabled=="boolean"&&this.ctx.shell.setManageEnabled(e.manage_enabled),this.selected=Math.min(this.selected,Math.max(0,(e.items?.length??0)-1))}):this.id==="bots"?(this.poll("/api/bots",1e4,e=>{this.bots=e,this.selected=Math.min(this.selected,Math.max(0,e.length-1))}),this.poll("/api/series/latency",1e4,e=>this.latency=e)):this.id==="dashboard"&&(this.poll("/api/overview",5e3,e=>this.overview=e),this.poll("/api/admin/power",5e3,e=>this.power=e),this.poll("/api/series/latency",8e3,e=>this.latency=e))}refresh=()=>{for(const e of this.pollers)e.tick()};choose(e,t){this.selected=(this.selected+e+Math.max(1,t))%Math.max(1,t)}refreshKey={label:"刷新遥测",action:()=>this.refresh()};selectMetric(e){this.metric=e}readout(){if(this.id==="navigation"){const o=this.ctx.host.actions.warping();return{title:"航点 "+(this.selected+1)+"/10 · "+vx[this.selected],value:o?"跃迁引擎工作中":"当前位置："+this.ctx.host.actions.systemName(),ratio:this.selected/9,keys:[{label:"上一航点",action:()=>this.choose(-1,10)},{label:"下一航点",action:()=>this.choose(1,10)},{label:"启动跃迁",disabled:o,action:()=>{this.ctx.host.actions.triggerWarp(!0,this.selected)}},{label:"天鹅座 λ-4",action:()=>{this.selected=0}},{label:"南门二 β",action:()=>{this.selected=2}},{label:"天琴座 Vega",action:()=>{this.selected=9}}]}}if(this.id==="plugins"){const o=this.plugins?.items??[],a=o[this.selected],l=!a?.id||a.manageable===!1||this.ctx.shell.availability("plugins").readOnly||this.plugins?.manage_enabled===!1,c=a?[a.status||(a.enabled?"已启用":"已停用"),a.disabled_reason||a.dependency_issues?.join("；")||"依赖："+(a.dependencies?.join(", ")||"无"),"v"+(a.version??"—")+" · "+(a.author??"未知作者")]:["尚无模块数据"];return{title:a?"模块 "+(this.selected+1)+"/"+o.length+" · "+a.name:"模块装配架",value:l&&a?"只读 · "+c[this.metric%c.length]:c[this.metric%c.length],ratio:a?a.status==="running"?1:a.enabled===!1?0:.5:null,keys:[{label:"上个模块",disabled:!o.length,action:()=>this.choose(-1,o.length)},{label:"下个模块",disabled:!o.length,action:()=>this.choose(1,o.length)},{label:a?.enabled===!1?"装载模块":"停用模块",disabled:l,danger:a?.enabled!==!1,action:()=>this.pluginOperation("toggle")},{label:"重载模块",disabled:l||a?.official===!0||a?.hot_reload===!1,danger:!0,action:()=>this.pluginOperation("reload")},{label:"状态 / 依赖",action:()=>{this.metric++}},this.refreshKey]}}if(this.id==="bots"){const o=this.bots??[],a=o[this.selected],l=a?!!a.online:null,c=a?[(l?"链路在线":"链路离线")+" · "+String(a.user_id??"—"),"今日消息 "+vt(Number(a.today_messages??0))+" / 累计 "+vt(Number(a.total_messages??0)),"平台 "+String(a.platform||a.app_name||"—")+" · 在线 "+ni(Number(a.uptime_seconds??0)),"链路延迟 "+String(a.latency_ms??this.latency?.current_ms??"—")+" ms"]:["尚无机器人数据"];return{title:a?"机器人 "+(this.selected+1)+"/"+o.length+" · "+String(a.nickname||a.name||"未命名"):"通讯链路选择器",value:c[this.metric%c.length],ratio:l===null?null:l?1:0,keys:[{label:"上个机器人",disabled:!o.length,action:()=>this.choose(-1,o.length)},{label:"下个机器人",disabled:!o.length,action:()=>this.choose(1,o.length)},{label:"连接状态",action:()=>this.selectMetric(0)},{label:"消息 / 平台",action:()=>this.selectMetric(this.metric===1?2:1)},{label:"链路延迟",action:()=>this.selectMetric(3)},this.refreshKey]}}if(this.id==="system"){const o=this.system,a=[o?.cpu_percent,o?.mem_percent,o?.disk_percent],l=["CPU 负载","内存占用","磁盘占用","后台任务","宿主服务"],c=this.metric<3?a[this.metric]==null?"等待真实遥测":a[this.metric].toFixed(1)+"%":this.metric===3?this.tasks?"定时 "+(this.tasks.scheduled?.length??0)+" · 后台 "+(this.tasks.background?.length??0):"任务数据未加载":this.services?(this.services.items??[]).map(h=>(h.available===!1?"○ ":"● ")+h.name).join(" / ")||"无已注册服务":"服务数据未加载";return{title:"太阳核心 · "+l[this.metric],value:c,ratio:this.metric<3&&a[this.metric]!=null?a[this.metric]/100:null,keys:[...l.map((h,u)=>({label:h,action:()=>this.selectMetric(u)})),this.refreshKey]}}if(this.id==="usage"){const o=this.usage?.items??[],a=this.selected===0?this.usage?.totals:o[this.selected-1],l=[a?.calls,a?.input_tokens,a?.output_tokens,a?.cost_cny],c=["调用次数","输入 Token","输出 Token","花费"],h=l[this.metric],u=[200,5e5,2e5,20];return{title:"24h · "+(this.selected===0?"全模块":o[this.selected-1]?.module??"未知模块")+" · "+c[this.metric],value:this.usage?.available===!1?"用量数据库不可用":h==null?"等待真实用量":(this.metric===3?Rs(h):this.metric===0?vt(h):Zi(h))+" · 刻度上限 "+u[this.metric],ratio:h==null?null:h/u[this.metric],keys:[{label:"调用次数",action:()=>this.selectMetric(0)},{label:"输入 / 输出",action:()=>this.selectMetric(this.metric===1?2:1)},{label:"实际花费",action:()=>this.selectMetric(3)},{label:"上个模块",action:()=>this.choose(-1,o.length+1)},{label:"下个模块",action:()=>this.choose(1,o.length+1)},this.refreshKey]}}const e=this.ctx.shell.status,t=this.overview,n=this.power?.standby??e.standby,i=["全舰总览","插件装载","消息吞吐","链路延迟"],r=[(n?"待机":"运行")+" · "+(e.online?"通讯在线":"通讯离线")+" · "+ni(t?.uptime_seconds??e.uptime_seconds),"运行 "+e.plugins.running+"/"+e.plugins.total+" · 错误 "+e.plugins.error,t?"今日 "+vt(t.today_messages)+" · 累计 "+vt(t.total_messages):"等待消息数据",this.latency?.current_ms==null?"等待链路数据":this.latency.current_ms.toFixed(0)+" ms"];return{title:"主控台 · "+i[this.metric%4],value:r[this.metric%4],ratio:this.metric%4===1&&e.plugins.total?e.plugins.running/e.plugins.total:null,keys:[{label:"切换监控",action:()=>{this.metric=(this.metric+1)%4}},this.refreshKey,{label:n?"恢复运行":"进入待机",danger:!n,action:()=>this.powerOperation(n?"resume":"standby")},{label:"软重启运行",danger:!0,action:()=>this.powerOperation("reboot")},{label:"重启 NeoBot",danger:!0,action:()=>this.powerOperation("restart")},{label:"插件监控",action:()=>this.selectMetric(1)}]}}async pluginOperation(e){const t=this.plugins?.items?.[this.selected];if(!t?.id||t.manageable===!1||this.plugins?.manage_enabled===!1||this.ctx.shell.availability("plugins").readOnly||e==="reload"&&(t.official===!0||t.hot_reload===!1))return;const n=t.enabled===!1,i=(e==="reload"?"重载模块 ":n?"装载模块 ":"停用模块 ")+t.name;await this.confirmPost(i,e==="reload"?"重新导入并重启模块，期间功能暂不可用。":n?"立即装载并启动模块。":"立即停止模块，依赖它的模块会被联动停用。"+(t.dependents?.length?" 被依赖："+t.dependents.join("、"):""),"/api/plugins/"+encodeURIComponent(t.id)+"/"+e,{},!0,()=>!this.ctx.shell.availability("plugins").readOnly&&this.plugins?.manage_enabled!==!1&&this.plugins?.items?.some(r=>r.id===t.id&&r.manageable!==!1&&r.enabled===t.enabled)===!0)}async powerOperation(e){const t={resume:"恢复运行",standby:"进入待机",reboot:"软重启运行",restart:"重启 NeoBot 进程"};await this.confirmPost(t[e],e==="restart"?"整个 NeoBot 进程将重启，网页连接会暂时断开。":e==="standby"?"停止回复与记忆管线，仅保留核心服务与面板。":"重新装配运行时，消息处理会短暂中断。","/api/admin/"+e,e==="restart"?{}:{reason:"星舰实体主控台"+t[e]},e!=="resume")}async confirmPost(e,t,n,i,r,o=()=>!0){if(!(this.busy||this.disposed||!this.focused)){this.busy=!0,this.sync();try{if(!await this.ctx.confirm({title:e,body:t,confirmLabel:"确认执行",danger:r})||this.disposed||!this.focused||!this.available||!o())return;const a=await this.ctx.host.consoleApi.post(n,i);if(this.disposed)return;this.ctx.toast(a.ok?a.data?.message||"指令已执行":a.error||"操作失败",a.ok?"ok":"error"),this.refresh()}catch(a){this.disposed||this.ctx.toast(a instanceof Error?a.message:"指令失败","error")}finally{this.busy=!1,this.disposed||(this.ctx.redraw(),this.sync())}}}activate(e){if(!this.focused||!this.available||this.busy||this.disposed)return;this.keys=this.readout().keys;const t=this.keys[e];!t||t.disabled||(t.action(),this.ctx.redraw(),this.sync())}hover(e,t){const n=this.hovered!==e||this.pressed!==t;this.hovered=e,this.pressed=t;for(const i of this.targets){const r=i===e?1.035:1;i.scale.set(r,r,i===e&&t?.7:1)}n&&this.sync()}setAvailability(e,t){this.available=e,this.reason=t,this.sync()}onFocus(){this.focused=!0,this.sync()}onBlur(){this.focused=!1,this.hover(null,!1),this.sync()}draw(e){this.sync()}sync(){if(this.disposed)return;const e=this.readout();this.keys=e.keys;const t=this.errors.values().next().value,n=[...e.keys.map(l=>l.label),e.title,this.available?this.busy?"等待确认 / 执行指令…":t?"遥测异常："+t:e.value:this.reason||"设备离线"],i=e.keys.map(l=>!this.available||this.busy||!!l.disabled),r=JSON.stringify([n,i,e.ratio,this.focused,this.hovered?.userData.physicalAction,this.pressed]);if(r===this.signature)return;this.signature=r,this.labelMaterial.depthWrite=this.focused,this.labelMaterial.opacity=this.focused?1:.38;const o=this.atlas.getContext("2d");o.setTransform(4,0,0,1,0,0),o.textAlign="center",o.textBaseline="middle",o.clearRect(0,0,512,1024);for(let l=0;l<8;l++){const c=l<6&&this.hovered===this.targets[l];o.globalAlpha=this.focused?1:.68;const h={x:0,y:l*128,w:512,h:128};l<6?fl(o,h,{hovered:c,pressed:c&&this.pressed,disabled:i[l],danger:e.keys[l].danger}):l===6?tu(o,h):(o.fillStyle="#071423",o.fillRect(h.x,h.y,h.w,h.h)),o.globalAlpha=this.focused?1:.55,o.fillStyle=l<6&&i[l]?"#a8b7c4":l===7&&t?"#ffc69a":"#edf9ff",o.font=(l<6?"600 44px":"32px")+' "Microsoft YaHei", system-ui, sans-serif',o.save(),o.translate(256,l*128+64);const u=Fs(this.id),d=l<6?4*this.targets[l].userData.labelHeight/this.targets[l].userData.labelWidth:4*.19/(u.width-.08);o.scale(d,1),o.fillText(n[l]??"",0,0,462/d),o.restore()}o.globalAlpha=1,this.runes.opacity=this.focused?.5:.24,this.hologram.opacity=this.focused?.13:.07,this.texture.needsUpdate=!0;const a=e.ratio==null||!this.available?null:_t.clamp(e.ratio,0,1);for(let l=0;l<24;l++)this.ring.setColorAt(l,new Ne(a!=null&&l<Math.ceil(a*24)?this.accent:1649463));this.ring.instanceColor&&(this.ring.instanceColor.needsUpdate=!0),this.needle.visible=a!=null,this.needle.rotation.y=Math.PI*.8-(a??0)*Math.PI*1.6}dispose(){this.disposed||(this.disposed=!0,this.pollers.forEach(e=>e.stop()),this.geometry.forEach(e=>e.dispose()),this.materials.forEach(e=>e.dispose()),this.ring.dispose(),this.texture.dispose(),this.group.removeFromParent())}}const yx=16754237;class Mx{constructor(e,t,n){this.host=t,this.definition=e,this.anchor=n,this.baseAccent=e.accent;const i=dx(t.materials,{accent:e.accent,title:e.title,stationId:e.id});this.screen=i.screen,this.group.add(i.group),e.decorate?.(this.decoration,t.materials),this.decoration.scale.setScalar(.24),this.decoration.position.set(0,.2,-.68),this.group.add(this.decoration),this.group.position.copy(n.position),this.group.rotation.y=n.yaw,t.scene.add(this.group),this.ui=new px(this.screen.canvas.width,this.screen.canvas.height,"#"+e.accent.toString(16).padStart(6,"0"),this.screen.canvas);const r={host:t,anchor:n,ui:this.ui,shell:t.shell,redraw:()=>this.markDirty(),toast:(o,a)=>t.toast(o,a),confirm:o=>t.confirm(o)};this.physical=xx(e.id,r,e.accent),this.controller=this.physical??e.create?.(r)??null,this.physical&&(this.screen.setBusinessControls(this.physical.group,this.physical.targets),this.decoration.visible=!1),this.drawFrame(!1)}definition;anchor;group=new qe;screen;ui;controller=null;physical=null;active=!1;dirty=!0;idleAccumulator=0;availability={available:!0,reason:"",hint:"",readOnly:!1};baseAccent;disposed=!1;decoration=new qe;lastScrollId=null;override=null;solidMeshes(){this.group.updateWorldMatrix(!0,!0);const e=[];return this.group.traverseVisible(t=>{t instanceof ve&&t.userData.solidConsole===!0&&e.push(t)}),e}get available(){return this.availability.available}get focused(){return this.active}get interactable(){return this.availability.available}get availabilityReason(){return this.availability.reason||"当前状态不可用"}markDirty(){this.dirty=!0}setOverride(e){this.override=e,this.markDirty()}setAvailability(e){const t=e.available!==this.availability.available||e.reason!==this.availability.reason||e.hint!==this.availability.hint||e.readOnly!==this.availability.readOnly;if(this.availability=e,this.physical?.setAvailability(e.available,e.reason),this.screen.setAccent(e.available?this.baseAccent:yx),t){if(this.active)for(const n of this.controller?.pollers??[])e.available?n.start(!0):n.stop();this.markDirty()}}get operatingSurface(){return this.physical?.operatingSurface??this.screen.mesh}focusView(){if(this.physical){const e=Fs(this.definition.id);return Qc(this.physical.operatingSurface,e.width,e.height,this.host.camera)}return Qc(this.screen.mesh,this.screen.width,this.screen.height,this.host.camera)}focus(){if(!(this.active||this.disposed)){if(this.active=!0,this.screen.setFocused(!0),this.decoration.visible=!1,this.controller?.onFocus?.(),this.available)for(const e of this.controller?.pollers??[])e.start(!0);this.markDirty()}}blur(){if(this.active){this.active=!1,this.screen.setFocused(!1),this.decoration.visible=!this.physical,this.screen.pressKey(null),this.ui.clicked=!1,this.clearPointer(),this.controller?.onBlur?.();for(const e of this.controller?.pollers??[])e.stop();this.markDirty()}}clearPointer(){this.ui.cursor.inside&&this.markDirty(),this.ui.cursor.inside=!1,this.ui.cursor.down=!1,this.ui.cursor.x=this.ui.cursor.y=-1e5,this.ui.clicked=!1,this.ui.hoverId=null}handlePointer(e,t,n){if(this.screen.pressKey(null),!this.active||!this.available||this.disposed){this.clearPointer();return}if(this.physical){this.clearPointer();const h=e?.object.userData.physicalAction;this.physical.hover(typeof h=="number"?e.object:null,this.host.input.pointer.down),t&&typeof h=="number"&&this.physical.activate(h);return}const i=e?.object.userData.consoleKey;if(i){if(this.clearPointer(),(this.host.input.pointer.down||t)&&this.screen.pressKey(e.object),t&&!this.override){if(i==="refresh"){for(const h of this.controller?.pollers??[])h.tick();this.host.toast("控制台数据已请求刷新","info")}else this.lastScrollId?this.ui.scrollBy(this.lastScrollId,i==="scroll-up"?-3:3):this.host.toast("先将光标移到列表，再使用上下实体键","info");this.markDirty()}return}if(!e?.uv){this.clearPointer();return}const r=_t.clamp(e.uv.x,0,1)*this.ui.width,o=(1-_t.clamp(e.uv.y,0,1))*this.ui.height,a=!this.ui.cursor.inside||Math.abs(r-this.ui.cursor.x)>.5||Math.abs(o-this.ui.cursor.y)>.5;this.ui.cursor.x=r,this.ui.cursor.y=o,this.ui.cursor.inside=!0,this.ui.cursor.down=this.host.input.pointer.down;const c=this.ui.hitTest(r,o)?.match(/^(.*):[0-9]+$/);c&&(this.lastScrollId=c[1]),t&&(this.ui.clicked=!0),(a||t)&&this.markDirty(),n!==0&&c&&(this.ui.scrollBy(c[1],n*.05),this.markDirty())}update(e){if(this.disposed)return;const t=this.active;if(this.screen.update(e,t),this.physical&&t&&this.physical.sync(),!t){this.ui.cursor.inside=!1;const n=this.definition.id!==""&&this.controller?.idleAnimated===!0,i=this.host.quality.refreshIdleTerminals?1:n?.4:0;i>0&&(this.idleAccumulator+=e,this.idleAccumulator>=i&&(this.idleAccumulator=0,this.markDirty()))}this.dirty&&(this.dirty=!1,this.drawFrame(t))}drawFrame(e){const t=this.ui;if(this.physical){this.physical.sync(),t.clicked=!1;return}t.clicked=t.clicked&&e&&t.cursor.inside&&this.available;const n=t.clicked;t.hoverId=null,t.begin(1/30,this.definition.title,this.definition.subtitle);try{this.available?e?(this.availability.reason&&(t.text(24,92,"⚠ "+this.availability.reason,{size:17,color:t.theme.warn}),this.availability.hint&&t.text(24,116,this.availability.hint,{size:15,color:t.theme.textDim})),this.override?this.override(t,e):this.controller?.draw(t,e)):this.drawStandby(t):this.drawOffline(t)}finally{t.end(),t.clicked=!1,this.screen.texture.needsUpdate=!0,n&&this.markDirty()}}drawStandby(e){const t=e.ctx;t.strokeStyle=e.theme.accent,t.lineWidth=3,t.beginPath(),t.moveTo(512,145),t.lineTo(574,244),t.lineTo(512,340),t.lineTo(450,244),t.closePath(),t.stroke(),e.text(512,402,"神 经 链 接 · 待 命",{size:30,align:"center",color:e.theme.accent}),e.text(512,450,"靠近并按 E 接入控制台",{size:24,align:"center"}),e.text(512,520,"KHALAI COMMAND INTERFACE",{size:16,align:"center",color:e.theme.textDim})}drawOffline(e){const t=e.ctx,n=performance.now()/1e3,i=e.width,r=e.height;t.save(),t.fillStyle="rgba(4, 8, 12, 0.97)",t.fillRect(0,0,i,r),t.strokeStyle="rgba(255, 166, 61, 0.35)",t.lineWidth=2;for(let o=0;o<14;o+=1){const a=(o/14*r+n*26)%r;t.beginPath(),t.moveTo(0,a),t.lineTo(i,a),t.stroke()}t.fillStyle="rgba(255, 166, 61, "+(.55+.35*Math.sin(n*3)).toFixed(3)+")",t.font='bold 42px "Microsoft YaHei", system-ui, sans-serif',t.textAlign="center",t.fillText("终 端 已 下 线",i/2,r/2-60),t.font='24px "Microsoft YaHei", system-ui, sans-serif',t.fillStyle="rgba(255, 200, 150, 0.9)",t.fillText(this.availability.reason||"该面板当前不可用",i/2,r/2+4),this.availability.hint&&(t.font='20px "Microsoft YaHei", system-ui, sans-serif',t.fillStyle="rgba(200, 220, 235, 0.75)",t.fillText(this.availability.hint,i/2,r/2+44)),t.font='18px "Microsoft YaHei", system-ui, sans-serif',t.fillStyle="rgba(255, 166, 61, 0.7)",t.fillText("LOW POWER MODE · "+this.definition.title,i/2,r-40),t.restore()}dispose(){if(this.disposed)return;this.disposed=!0,this.blur(),this.controller?.dispose?.(),this.host.scene.remove(this.group),this.screen.dispose();const e=new Set(Object.values(this.host.materials)),t=new Set;for(const o of e)for(const a of Object.values(o))a instanceof It&&t.add(a);const n=new Set,i=new Set,r=new Set;this.decoration.traverse(o=>{if(o instanceof ve){n.add(o.geometry);for(const a of Array.isArray(o.material)?o.material:[o.material])if(!e.has(a)){i.add(a);for(const l of Object.values(a))l instanceof It&&!t.has(l)&&r.add(l)}}}),n.forEach(o=>o.dispose()),i.forEach(o=>o.dispose()),r.forEach(o=>o.dispose()),this.group.clear()}}const Va=new Map;function bx(s){if(!s.id||Va.has(s.id))throw new Error("Duplicate or empty vessel ID: "+s.id);Va.set(s.id,s)}function th(s){const e=Va.get(s);if(!e)throw new Error("Vessel is not implemented: "+s);return e}const Ha="psionic-ark";bx({id:Ha,label:"星灵风格 · 灵能方舟",instruments:nu,build:Kv});class wx{constructor(e){this.group=e}batches=new Map;add(e,t,n=[0,0,0],i=[0,0,0]){e.applyMatrix4(new Fe().compose(new w(...n),new Pt().setFromEuler(new Yt(...i)),new w(1,1,1)));const r=e.index?e.toNonIndexed():e;r!==e&&e.dispose(),r.deleteAttribute("uv");const o=this.batches.get(t)??[];o.push(r),this.batches.set(t,o)}box(e,t,n){this.add(new lt(...t),n,e)}profile(e,t,n,i,r=[0,0,0],o=.12){const a=new xt(e,{depth:t,steps:1,curveSegments:18,bevelEnabled:o>0,bevelSize:o,bevelThickness:o,bevelSegments:2});a.translate(0,0,-t/2),this.add(a,n,i,r)}finish(){let e=0;for(const[t,n]of this.batches){const i=cs(n,!1);if(n.forEach(o=>o.dispose()),!i)throw new Error("Incompatible foundry architecture geometry");i.computeBoundingSphere();const r=new ve(i,t);r.name=this.group.name+"-surface-"+e++,r.receiveShadow=!0,r.matrixAutoUpdate=!1,this.group.add(r)}}}function mt(s,e){const t=new De;return t.moveTo(0,-e*.52),t.bezierCurveTo(-s*.42,-e*.25,-s*.56,e*.18,-s*.31,e*.31),t.quadraticCurveTo(-s*.1,e*.43,0,e*.53),t.quadraticCurveTo(s*.1,e*.43,s*.31,e*.31),t.bezierCurveTo(s*.56,e*.18,s*.42,-e*.25,0,-e*.52),t}function Sx(){const s=new De;return s.moveTo(30.6,0),s.bezierCurveTo(32.8,12,32,25,26,33),s.bezierCurveTo(21,40,12,44,4.8,48),s.bezierCurveTo(18,48,31,43,36.1,31),s.bezierCurveTo(40.8,20,37.3,7,36.9,0),s.closePath(),s}function Tx(){const s=new De;return s.moveTo(33.05,6),s.bezierCurveTo(36,21,31.6,32,27,36.5),s.quadraticCurveTo(19,43,10.4,46.2),s.bezierCurveTo(22,44,32.5,38.8,35,29),s.quadraticCurveTo(39,17,33.05,6),s}function Ex(){const s=new De;return s.moveTo(31.8,8),s.bezierCurveTo(34,24,29,34,21,40.2),s.quadraticCurveTo(14,45,7.8,47),s.quadraticCurveTo(14,44.6,20.9,40),s.bezierCurveTo(28.6,33.6,33.5,23.8,31.65,8),s}function nh(){const s=new De;return s.moveTo(79,-8.3),s.lineTo(79,8.3),s.bezierCurveTo(67,8.5,48,7.8,37.5,0),s.bezierCurveTo(48,-7.8,67,-8.5,79,-8.3),s}function Ax(s,e,t,n,i,r){const o=[0,-Math.PI/2,0];s.profile(mt(3.7,7.2),1.2,i.ceiling,[e,t+7,n],o),s.profile(mt(2.8,5.8),.3,i.prop,[e-.78,t+7.2,n],o),s.profile(mt(1.35,4.3),.17,i.ceiling,[e-1,t+7.2,n],o),s.profile(mt(.36,2),.08,r,[e-1.14,t+7.5,n],o,.025);for(const a of[-1,1])s.profile(mt(1.2,5.3),.7,i.hull,[e,t+3.2,n+a*1.4],[a*.21,-Math.PI/2,0]),s.profile(mt(.9,5.9),.65,i.prop,[e+.35,t+7.2,n+a*2.7],[-a*.33,-Math.PI/2,0]),s.box([e-.15,t+1,n+a*1.85],[2.1,.5,.62],i.ceiling);s.profile(mt(1.7,3.4),.7,i.hull,[e,t+11.7,n],o),s.profile(mt(.35,1.7),.08,r,[e-.45,t+11.9,n],o,.02)}function Cx(s,e){const t=new qe;t.name="foundry-temple-architecture",t.userData.nonPlayable=!0,t.userData.layers=[15,32,50],t.userData.opaqueEnvelope={x:[-82,82],y:[-23,71],z:[13,59]};const n=new Ge({color:463651,toneMapped:!0});n.name="foundry-blue-abyss";const i=new Ge({color:4946846,toneMapped:!0});i.name="foundry-muted-cold-inlay";const r=new Ge({color:2112864,toneMapped:!0});r.name="foundry-distance-blue";const o=s;for(const a of e){const l=new qe;l.name=a<0?"war-forge-temple-wing":"robot-forge-temple-wing",l.scale.x=a,t.add(l);const c=new wx(l);c.box([81,24,36],[2,94,46],o.ceiling),c.box([56.5,-21,36],[51,2,46],o.ceiling),c.box([41,70,36],[82,2,46],o.ceiling);for(const h of[13.5,58.5]){c.box([57,24,h],[50,94,1],o.ceiling),c.box([18.75,7.5,h],[26.5,15,1],o.ceiling),c.box([16,43,h],[32,56,1],o.ceiling);for(const u of[12,25])c.profile(mt(9,23),1,o.prop,[u,12,h+(h<36?.75:-.75)]),c.profile(mt(7.2,20.5),.24,o.ceiling,[u,12,h+(h<36?1.5:-1.5)])}c.box([79.8,24,36],[.2,89,43],n);for(const h of[18.5,36.5,54.5])c.profile(mt(4.6,78),.3,r,[79.4,25,h],[0,-Math.PI/2,0]),c.profile(mt(1.2,66),.32,i,[79.1,25,h],[0,-Math.PI/2,0]);for(const h of[15.5,36.5,57]){c.profile(Sx(),3,o.prop,[0,0,h],[0,0,0],.24);for(const u of[-1,1]){c.profile(Tx(),.2,o.ceiling,[0,0,h+u*1.66]),c.profile(Ex(),.08,i,[0,0,h+u*1.8],[0,0,0],.01);for(let d=0;d<4;d++){const f=34.2+Math.sin(d*.6)*.4;c.profile(mt(2.5,5.2),.22,o.hull,[f,5.5+d*5.2,h+u*1.82]),c.profile(mt(1.5,3.8),.16,o.ceiling,[f,5.5+d*5.2,h+u*1.99])}}for(let u=0;u<3;u++){const d=57+u*6,f=14+u*17;c.profile(mt(7,23),3.2,o.hull,[d,f+5,h]),c.profile(mt(4.4,18),.3,o.ceiling,[d,f+5,h-1.85]),c.profile(mt(.3,12),.1,r,[d-.8,f+6,h-2.05])}}for(let h=0;h<3;h++){const u=[15,32,50][h];for(const d of[26,47]){c.profile(nh(),1.55,o.prop,[0,u,d],[Math.PI/2,0,0],.2),c.profile(nh(),.16,o.ceiling,[0,u+.98,d],[Math.PI/2,0,0],.05);const f=new De;f.moveTo(39,0),f.bezierCurveTo(48,-1,64,-3,78,-10),f.lineTo(79,0),f.closePath(),c.profile(f,2.7,o.hull,[0,u-.5,d]),c.profile(mt(2.6,8),.35,o.ceiling,[55,u-4.1,d-1.6],[0,0,-.62]);const g=new De;g.moveTo(39,0),g.bezierCurveTo(50,-6.3,68,-7.65,78,-7.5),g.lineTo(78,-7.37),g.bezierCurveTo(67,-7.5,50,-6.1,39,0),c.profile(g,.07,h===0?i:r,[0,u+.98,d],[Math.PI/2,0,0],0);const x=60+h*5;c.profile(mt(13.5,16),2,o.prop,[x+3,u+9,d],[0,-Math.PI/2,0],.25),c.profile(mt(11.4,14.5),.4,o.ceiling,[x+1.75,u+9,d],[0,-Math.PI/2,0]),Ax(c,x,u+1.1,d,o,h===0?i:r);for(const p of[-6.4,6.4])c.profile(mt(1.4,12.5),1.1,o.hull,[x-2,u+7,d+p],[0,-Math.PI/2,0]),c.profile(mt(.21,7),.07,r,[x-2.7,u+8,d+p],[0,-Math.PI/2,0],0)}}c.box([32.1,-3.5,36],[1,7,44],o.prop),c.box([32.7,-10,36],[1.1,8,44],o.ceiling);for(const h of[21,30,43,52])c.profile(mt(3.2,15),1.7,o.hull,[33.5,-7,h]),c.box([33.7,-15.5,h],[.2,.12,5.5],r);for(const h of[25,47])c.profile(mt(18,57),1.3,o.hull,[40,68.4,h],[Math.PI/2,0,Math.PI/2]),c.profile(mt(14,49),.3,o.ceiling,[40,67.5,h],[Math.PI/2,0,Math.PI/2]);c.finish();for(const h of[26,47]){const u=new Bn(6854092,95,38,2);u.name="foundry-recess-cold-bounce",u.position.set(40,18,h),l.add(u)}for(const h of[43,72]){const u=new gt({transparent:!0,depthWrite:!1,side:Dt,uniforms:{tint:{value:new Ne(3234448)},strength:{value:h===43?.16:.24}},vertexShader:`
          varying vec2 airUv;
          #include <common>
          #include <logdepthbuf_pars_vertex>
          void main() {
            airUv = uv;
            gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
            #include <logdepthbuf_vertex>
          }`,fragmentShader:`
          uniform vec3 tint;
          uniform float strength;
          varying vec2 airUv;
          #include <common>
          #include <logdepthbuf_pars_fragment>
          void main() {
            #include <logdepthbuf_fragment>
            vec2 q = airUv * 2.0 - 1.0;
            float edge = (1.0 - smoothstep(0.48, 1.0, abs(q.x))) * (1.0 - smoothstep(0.45, 1.0, abs(q.y)));
            float column = 0.46 + 0.54 * pow(0.5 + 0.5 * sin(airUv.x * 19.0 + airUv.y * 2.0), 4.0);
            float depth = 0.65 + 0.35 * smoothstep(-0.8, 0.8, q.y);
            gl_FragColor = vec4(tint, strength * edge * column * depth);
            #include <tonemapping_fragment>
            #include <colorspace_fragment>
          }`});u.name="foundry-local-blue-air";const d=new ve(new Gt(43,82),u);d.name="non-playable-depth-haze",d.position.set(h,26,36),d.rotation.y=Math.PI/2,l.add(d)}}return t}class au{root=new qe;a=new En(this.root);owned=[];metal(e,t,n){const i=e.clone();return i.name=n,i.color.setHex(t),Os(i,{scale:5,colourVariation:.045,roughnessVariation:.09,relief:25e-6}),this.owned.push(i),i}frame(e,t,n=[0,1,0]){const i=new w(...t).normalize(),r=new w(...n).cross(i).normalize();return new Fe().makeBasis(r,i.clone().cross(r),i).setPosition(...e)}shell(e,t,n=new Fe,i=0,r=Math.PI*2,o=.075,a=40,l=1){const c=r-i>Math.PI*1.999,h=[],u=(_,v,M,S,E)=>.5*(2*v+(-_+M)*E+(2*_-5*v+4*M-S)*E*E+(-_+3*v-3*M+S)*E*E*E);for(let _=0;_<e.length-1;_++)for(let v=0;v<5;v++){const M=v/5,S=e[_].map((E,C)=>u(e[Math.max(0,_-1)][C],e[_][C],e[_+1][C],e[Math.min(e.length-1,_+2)][C],M));S[3]=Math.max(.005,S[3]),S[4]=Math.max(.005,S[4]),h.push(S)}h.push(e[e.length-1]);const d=Math.max(8,Math.ceil(a*(r-i)/(Math.PI*2))),f=d+1,g=[],x=[];for(let _=0;_<(c?1:2);_++)for(const[v,M,S,E,C]of h)for(let z=0;z<=d;z++){const T=i+(r-i)*z/d,y=_*o,b=Math.sin(T),D=Math.cos(T);g.push(v+Math.sign(b)*Math.pow(Math.abs(b),l)*Math.max(.004,E-y),M,S+Math.sign(D)*Math.pow(Math.abs(D),l)*Math.max(.004,C-y))}const p=h.length*f;for(let _=0;_<(c?1:2);_++)for(let v=0;v<h.length-1;v++)for(let M=0;M<d;M++){const S=_*p+v*f+M,E=S+1,C=S+f;_===0?x.push(S,E,C,E,C+1,C):x.push(S,C,E,E,C,C+1)}if(c){const _=(h.length-1)*f;for(let v=1;v<d-1;v++)x.push(0,v+1,v,_,_+v,_+v+1)}else{for(let _=0;_<h.length-1;_++)for(const v of[0,d]){const M=_*f+v,S=M+f;v===0?x.push(M,S,M+p,S,S+p,M+p):x.push(M,M+p,S,S,M+p,S+p)}for(let _=0;_<d;_++)for(const v of[0,h.length-1]){const M=v*f+_,S=M+1;v===0?x.push(M,M+p,S,S,M+p,S+p):x.push(M,S,M+p,S,S+p,M+p)}}const m=new je;m.setAttribute("position",new Ae(g,3)),m.setIndex(x),m.computeVertexNormals(),this.a.add(m.applyMatrix4(n),t)}line(e,t,n){this.a.curve(e,t,n,Math.max(12,e.length*7))}limb(e,t,n,i,r,o=!1){const a=new w(...t).sub(new w(...e)),l=a.length(),c=a.normalize(),h=new w(...n);h.addScaledVector(c,-c.dot(h)).normalize();const u=this.frame(e,h.toArray(),c.toArray());this.shell(i.map(([d,f,g,x])=>[0,d*l,x,f,g]),r,u,o?-1.92:0,o?1.92:Math.PI*2,.07,32,o?.64:1)}plate(e,t,n,i=.1){const r=new xt(e,{depth:i,steps:1,bevelEnabled:!0,bevelSize:.028,bevelThickness:.023,bevelSegments:3,curveSegments:20});this.a.add(r.applyMatrix4(n),t)}optic(e,t,n,i,r,o,a,l){const c=this.frame(e,t),h=(u,d)=>this.a.add(u.applyMatrix4(c),d);h(new et(1,1,.09,32).rotateX(Math.PI/2).scale(n*1.22,i*1.18,1),o),h(new at(1,.105,8,48).scale(n,i,.6).translate(0,0,.035),r),h(new ft(1,28,16).scale(n*.88,i*.89,.075).translate(0,0,.034),a),h(new at(1,.025,6,40).scale(n*.77,i*.8,.5).translate(0,0,.103),l)}joint(e,t,n,i,r,o){const a=this.frame(e,t),l=(c,h)=>this.a.add(c.applyMatrix4(a),h);l(new et(n,n,.22,24).rotateX(Math.PI/2),r),l(new at(n*.79,n*.11,8,32).translate(0,0,.12),i),l(new et(n*.44,n*.44,.045,16).rotateX(Math.PI/2).translate(0,0,.135),o);for(let c=0;c<5;c++){const h=c*Math.PI*2/5;l(new et(.023,.023,.025,8).rotateX(Math.PI/2).translate(Math.cos(h)*n*.77,Math.sin(h)*n*.77,.15),r)}}finish(e,t,n,i){this.a.finish();const r=new Lt().setFromObject(this.root),o=r.getSize(new w),a=t/o.y,l=e==="dragoon"?1.12:1,c=Math.min(a*l,n/o.x),h=Math.min(a*l,i/o.z),u=r.getCenter(new w),d=new Fe().makeScale(c,a,h).setPosition(-u.x*c,-r.min.y*a,-u.z*h);return this.root.traverse(f=>{f instanceof ve&&(f.geometry.applyMatrix4(d),f.geometry.computeBoundingBox(),f.geometry.computeBoundingSphere(),f.castShadow=!0,f.receiveShadow=!0,f.name=e+"-"+f.material.name)}),this.root.name="protoss-"+e,this.root.userData={unitKind:e,label:e==="stalker"?"追猎者":"龙骑士",forwardAxis:"-z",ownedMaterials:this.owned,displayDimensions:[o.x*c,t,o.z*h]},this.root}}function Px(s){const e=new au,t=e.metal(s.hull,6574447,"stalker-platinum-violet"),n=e.metal(s.wallAccent,11839167,"stalker-cut-platinum"),i=e.metal(s.wall,3747662,"stalker-recessed-ceramic"),r=e.metal(s.ceiling,1250850,"stalker-joint-obsidian"),o=e.metal(s.wall,1194610,"stalker-optical-glass");o.emissive.setHex(1202105),o.emissiveIntensity=.55,o.roughness=.16;const a=s.trim,l=[[0,2.65,.16,.34,.39],[0,2.98,.1,.65,.61],[0,3.45,-.03,.89,.78],[0,4.03,-.26,1.05,.87],[0,4.62,-.05,.84,.74],[0,5.1,.3,.48,.48],[0,5.44,.59,.18,.2],[0,5.64,.73,.018,.045]];e.shell(l,r);for(const c of[-1,1]){const h=new Fe().makeTranslation(c*.12,0,0),u=c===1?.26:Math.PI+.26,d=c===1?Math.PI-.25:Math.PI*2-.25;e.shell(l,t,h,u,d,.15,56,.79);const f=[[c*.65,3.04,.03,.1,.27],[c*.91,3.6,-.13,.24,.55],[c*1.01,4.22,-.12,.2,.53],[c*.71,4.85,.25,.16,.44],[c*.39,5.29,.54,.085,.21],[c*.11,5.57,.7,.018,.05]];e.shell(f,t),e.line([[c*.68,3.1,-.2],[c*1.12,3.82,-.54],[c*1.12,4.4,-.6],[c*.57,5.03,-.1],[c*.11,5.6,.68]],.035,n),e.line([[c*.65,3.11,.36],[c*1.1,3.9,.58],[c*.81,4.65,.73],[c*.33,5.27,.79]],.026,n),e.optic([c*1.185,4.2,-.36],[c*.96,.06,-.29],.245,.39,n,r,o,a);const g=new De;g.moveTo(-.12,-.12),g.lineTo(-.14,.24),g.quadraticCurveTo(-.08,.42,.035,.58),g.lineTo(.12,.15),g.lineTo(.07,-.16),g.closePath(),e.plate(g,i,e.frame([c*1.02,4.63,-.03],[c*.94,.28,-.17]),.025);for(let x=0;x<3;x++)e.line([[c*1.245,3.6+x*.13,-.1],[c*1.25,3.62+x*.13,.04]],.018,r);e.optic([c*.73,3.15,-.56],[c*.65,-.1,-.76],.115,.19,t,r,o,a);for(let x=0;x<3;x++){const p=3.68+x*.22;e.line([[c*.42,p,-.86],[c*.63,p+.055,-.86],[c*.78,p+.12,-.77]],.035,r),e.line([[c*.43,p+.045,-.868],[c*.62,p+.098,-.856]],.012,n)}e.shell([[c*.28,3.03,-.87,.05,.15],[c*.49,3.3,-1,.16,.22],[c*.53,3.65,-1.03,.19,.22],[c*.41,3.95,-.97,.12,.18]],t,new Fe,1.65,4.63,.09,40,.68),e.line([[c*.2,3.11,-1.03],[c*.45,3.35,-1.21],[c*.49,3.67,-1.22]],.022,n)}e.shell([[0,3.66,-1.22,.14,.17],[0,3.9,-1.12,.4,.29],[0,4.25,-1,.4,.31],[0,4.65,-.63,.28,.25],[0,5.02,-.15,.19,.2],[0,5.38,.39,.075,.13],[0,5.64,.74,.012,.03]],n,new Fe,0,Math.PI*2,.08,40,.73),e.shell([[0,3.92,-1.37,.035,.025],[0,4.28,-1.19,.15,.05],[0,4.67,-.86,.1,.05],[0,5.11,-.18,.05,.04],[0,5.51,.5,.008,.02]],i),e.shell([[0,3.07,-1.13,.12,.11],[0,3.24,-1.28,.24,.2],[0,3.56,-1.26,.29,.17],[0,3.75,-1.17,.2,.12]],r);for(const c of[-1,1])e.line([[c*.065,3.59,-1.438],[c*.15,3.63,-1.44],[c*.25,3.61,-1.39]],.024,a),e.shell([[c*.12,3.16,-1.3,.035,.08],[c*.19,3.34,-1.42,.1,.14],[c*.23,3.51,-1.34,.095,.1]],t),e.line([[c*.08,3.21,-1.44],[c*.13,3.31,-1.57],[c*.2,3.44,-1.48]],.018,n);e.optic([0,3.27,-1.57],[0,-.06,-1],.105,.075,n,r,o,a);for(const c of[-1,1])e.shell([[c*.39,5.05,.13,.14,.2],[c*.4,5.23,.09,.11,.14],[c*.36,5.42,-.01,.015,.03]],o);e.shell([[0,2.3,.12,.31,.32],[0,2.58,.12,.6,.55],[0,2.84,.12,.7,.62],[0,3.06,.13,.53,.47]],r);for(let c=0;c<4;c++)e.line([[-.47,2.43+c*.13,-.25],[0,2.39+c*.13,-.49],[.47,2.43+c*.13,-.25]],.027,i);for(const c of[-1,1])for(const h of[-1,1]){const u=[c*.66,2.81,h*.45],d=[c*1.47,2.38,h*1.25],f=[c*2.1,2.23,h*1.94],g=[c*2.61,.48,h*2.58],x=[c*2.84,.025,h*2.92],p=[c*.68,.1,h*.73];e.joint(u,p,.25,n,r,i);for(const M of[-.12,.12]){const S=[u[0],u[1]+M,u[2]],E=[d[0],d[1]+M,d[2]];e.limb(S,E,p,[[0,.08,.07,0],[.23,.12,.1,.03],[.8,.09,.075,0],[1,.07,.07,0]],M>0?t:r)}e.joint(d,p,.19,t,r,i),e.limb(d,f,p,[[0,.1,.07,0],[.25,.2,.085,.02],[.72,.18,.085,.02],[1,.11,.065,0]],t,!0),e.line([[u[0],u[1]-.15,u[2]],[c*1.35,2.06,h*1.15],[f[0],f[1]-.13,f[2]]],.043,r),e.joint(f,p,.27,n,r,o);const m=new De;m.moveTo(-.17,-.12),m.quadraticCurveTo(-.25,.28,-.17,.7),m.lineTo(.04,.95),m.quadraticCurveTo(.07,.4,.22,.03),m.lineTo(.15,-.14),m.closePath();const _=new vi;_.moveTo(-.075,.25),_.lineTo(-.1,.58),_.lineTo(.006,.7),_.lineTo(.032,.29),_.closePath(),m.holes.push(_),e.plate(m,t,e.frame([c*1.99,2.33,h*1.82],p),.13),e.limb(g,f,p,[[0,.06,.06,0],[.26,.12,.08,.045],[.6,.21,.1,.075],[.88,.23,.095,.045],[1,.15,.08,0]],t,!0);const v=[c*2.22,1.88,h*2.08];e.limb(v,f,p,[[0,.14,.08,.09],[.5,.24,.11,.09],[1,.18,.09,.02]],n,!0),e.line([[c*2.17,2,h*1.87],[c*2.35,1.24,h*2.15],[c*2.53,.55,h*2.45]],.045,r),e.line([[c*2.17,2.02,h*2.08],[c*2.42,1.3,h*2.43],[c*2.66,.53,h*2.7]],.017,i),e.limb(g,f,p,[[.15,.018,.01,.14],[.42,.026,.014,.18],[.7,.03,.012,.2],[.88,.012,.008,.17]],i),e.joint(g,p,.12,t,r,i),e.limb(x,g,p,[[0,.009,.013,0],[.2,.055,.03,.01],[.7,.1,.07,.035],[1,.07,.055,0]],n,!0)}return e.finish("stalker",5.6,6.4,6.4)}function Rx(s){const e=new au,t=e.metal(s.hull,11837803,"dragoon-burnished-gold"),n=e.metal(s.wallAccent,14797713,"dragoon-cut-electrum"),i=e.metal(s.prop,7889733,"dragoon-recess-bronze"),r=e.metal(s.ceiling,1448739,"dragoon-undercut-obsidian"),o=e.metal(s.wall,2505561,"dragoon-cobalt-enamel"),a=e.metal(s.wall,1332373,"dragoon-optical-glass");a.emissive.setHex(1212105),a.emissiveIntensity=.35,a.roughness=.16;const l=s.trim,c=[[0,2.12,.1,.39,.45],[0,2.34,.08,.74,.72],[0,2.64,.03,1.02,.89],[0,3,.01,1.3,1.16],[0,3.28,0,1.41,1.24]];e.shell(c,r);for(let f=0;f<3;f++){const g=2.38+f*.23;e.line([[-.64-f*.16,g,-.4],[0,g-.13,-.8-f*.12],[.64+f*.16,g,-.4]],.054,i)}const h=[[0,3.07,0,1.35,1.19],[0,3.38,.07,1.44,1.27],[0,3.66,.1,1.36,1.24],[0,3.96,.12,1.18,1.08],[0,4.16,.14,.85,.79],[0,4.27,.15,.43,.41],[0,4.29,.15,.025,.025]];e.shell(h,r);for(let f=0;f<8;f++){const g=f*Math.PI/4+.032,x=(f+1)*Math.PI/4-.032;e.shell(h,f===3||f===4?o:t,new Fe().makeTranslation(0,.025,0),g,x,.13,56)}const u=[[0,4.07,.15,.91,.85],[0,4.26,.15,.79,.74],[0,4.4,.15,.47,.44],[0,4.44,.15,.045,.045]];for(let f=0;f<4;f++)e.shell(u,t,new Fe,f*Math.PI/2+.035,(f+1)*Math.PI/2-.035,.065,48);e.line([[-.91,4.08,.15],[-.65,4.08,-.45],[0,4.08,-.7],[.65,4.08,-.45],[.91,4.08,.15],[.65,4.08,.75],[0,4.08,1],[-.65,4.08,.75],[-.91,4.08,.15]],.031,n),e.shell([[0,2.98,-1.04,.11,.1],[0,3.22,-1.15,.45,.15],[0,3.55,-1.11,.68,.13],[0,3.79,-.99,.62,.1],[0,4,-.74,.47,.06]],o);for(const f of[-1,1])e.line([[f*.1,3.03,-1.14],[f*.39,3.28,-1.3],[f*.7,3.66,-1.23],[f*.56,4,-.99]],.034,n);e.optic([0,3.27,-1.33],[0,-.05,-1],.17,.18,n,r,a,l);const d=new De;d.moveTo(-.72,0),d.quadraticCurveTo(-.65,.81,-.22,1.13),d.quadraticCurveTo(0,1.31,.22,1.13),d.quadraticCurveTo(.65,.81,.72,0),d.lineTo(.45,.06),d.quadraticCurveTo(.37,.65,0,.92),d.quadraticCurveTo(-.37,.65,-.45,.06),d.closePath(),e.plate(d,i,e.frame([0,3.85,.9],[0,0,1]),.15),e.line([[-.57,3.91,1.085],[-.4,4.53,1.085],[0,4.94,1.085],[.4,4.53,1.085],[.57,3.91,1.085]],.034,n),e.shell([[0,2.04,-.93,.1,.19],[0,2.26,-1.11,.2,.29],[0,2.52,-1.05,.24,.27],[0,2.77,-.76,.15,.2]],t),e.optic([0,2.31,-1.39],[0,-.12,-1],.115,.13,n,r,a,l);for(const f of[-1,1])for(const g of[-1,1]){const x=[f*.707,0,g*.707],p=(N,B)=>[x[0]*N,B,x[2]*N],m=p(1.3,2.98),_=p(2.38,3.58),v=p(3.21,2.83),M=p(3.83,.73),S=p(4.2,.035),E=[x[2],0,-x[0]];e.joint(m,x,.37,i,r,o),e.limb(m,_,x,[[0,.23,.24,0],[.35,.33,.29,.05],[.73,.31,.28,.1],[1,.23,.2,0]],r);const C=[[0,2.96,1.41,.34,.26],[0,3.23,1.57,.64,.53],[0,3.64,1.89,.7,.61],[0,4.02,2.13,.59,.39],[0,4.25,2.25,.41,.19],[0,4.35,2.36,.24,.08]],z=e.frame([0,0,0],x);e.shell(C,t,z,-1.65,1.65,.17,48),e.shell(C,o,z,1.74,2.44,.13,48),e.shell(C,t,z,3.84,4.55,.13,48);const T=[[0,3.45,2.38,.51,.18],[0,3.84,2.53,.5,.23],[0,4.16,2.63,.37,.12],[0,4.35,2.7,.24,.055]];e.shell(T,n,z,-1.35,1.35,.09,40,.65);const y=N=>new w(...N).applyMatrix4(z).toArray();for(const N of[-1,1])e.line([[N*.35,3.03,1.58],[N*.66,3.43,2.04],[N*.59,3.92,2.32],[N*.3,4.29,2.3]].map(B=>y(B)),.032,i);e.joint(_,E,.3,n,r,o),e.limb(_,v,x,[[0,.24,.13,0],[.34,.32,.17,.1],[.7,.28,.16,.12],[1,.21,.12,0]],i,!0),e.line([p(2.19,3.3),p(2.58,2.98),p(3.05,2.66)],.095,r),e.joint(v,E,.29,n,r,o),e.limb(M,v,x,[[0,.1,.09,0],[.26,.13,.1,.03],[.59,.17,.12,.04],[.87,.2,.12,.025],[1,.16,.1,0]],r);const b=p(3.76,.88),D=p(3.49,1.88),L=p(3.22,2.83);e.limb(D,L,x,[[0,.25,.12,.12],[.28,.41,.19,.15],[.72,.42,.2,.12],[1,.29,.14,.04]],t,!0),e.limb(b,D,x,[[0,.16,.11,.08],[.25,.28,.15,.13],[.72,.34,.18,.14],[1,.3,.15,.1]],t,!0),e.limb(M,b,x,[[0,.17,.12,.06],[.55,.24,.15,.1],[1,.22,.12,.06]],n,!0),e.limb(D,L,x,[[.16,.055,.016,.3],[.4,.14,.018,.355],[.69,.15,.018,.335],[.91,.055,.012,.23]],i),e.limb(D,L,x,[[.21,.045,.012,.32],[.42,.11,.016,.373],[.67,.12,.016,.351],[.85,.045,.01,.26]],o),e.limb(b,D,x,[[.14,.014,.01,.22],[.4,.022,.014,.3],[.73,.025,.013,.335],[.89,.012,.008,.28]],i);for(let N=0;N<2;N++){const B=p(3.56+N*.07,1.61-N*.18);e.line([[B[0]-E[0]*.11,B[1],B[2]-E[2]*.11],[B[0]+x[0]*.26,B[1]-.025,B[2]+x[2]*.26],[B[0]+E[0]*.11,B[1],B[2]+E[2]*.11]],.023,i)}e.joint(M,E,.19,i,r,o),e.limb(S,M,x,[[0,.035,.045,0],[.25,.13,.16,.06],[.7,.19,.21,.13],[1,.14,.16,.04]],r);for(const N of[-1,1]){const B=[S[0]+E[0]*N*.15,.03,S[2]+E[2]*N*.15],k=[M[0]+E[0]*N*.13,.57,M[2]+E[2]*N*.13];e.limb(B,k,x,[[0,.018,.025,0],[.3,.075,.075,.04],[.72,.11,.11,.09],[1,.075,.055,0]],t,!0)}e.limb(p(3.9,.34),p(3.78,.84),x,[[0,.05,.055,.15],[.5,.16,.16,.17],[1,.11,.1,.09]],o)}return e.finish("dragoon",5.2,7.4,7.4)}class Dx{constructor(e=.1,t=6){this.maxEdgeLength=e,this.maxIterations=t}modify(e){e.index!==null&&(e=e.toNonIndexed());const t=this.maxIterations,n=this.maxEdgeLength*this.maxEdgeLength,i=new w,r=new w,o=new w,a=new w,l=[i,r,o,a],c=new w,h=new w,u=new w,d=new w,f=[c,h,u,d],g=new Ne,x=new Ne,p=new Ne,m=new Ne,_=[g,x,p,m],v=new Q,M=new Q,S=new Q,E=new Q,C=[v,M,S,E],z=new Q,T=new Q,y=new Q,b=new Q,D=[z,T,y,b],L=e.attributes,N=L.normal!==void 0,B=L.color!==void 0,k=L.uv!==void 0,q=L.uv1!==void 0;let U=L.position.array,V=N?L.normal.array:null,P=B?L.color.array:null,O=k?L.uv.array:null,H=q?L.uv1.array:null,Z=U,W=V,$=P,le=O,he=H,Ce=0,Oe=!0;function Ie(te,I,ce){const ae=l[te],se=l[I],de=l[ce];if(Z.push(ae.x,ae.y,ae.z),Z.push(se.x,se.y,se.z),Z.push(de.x,de.y,de.z),N){const xe=f[te],pe=f[I],F=f[ce];W.push(xe.x,xe.y,xe.z),W.push(pe.x,pe.y,pe.z),W.push(F.x,F.y,F.z)}if(B){const xe=_[te],pe=_[I],F=_[ce];$.push(xe.r,xe.g,xe.b),$.push(pe.r,pe.g,pe.b),$.push(F.r,F.g,F.b)}if(k){const xe=C[te],pe=C[I],F=C[ce];le.push(xe.x,xe.y),le.push(pe.x,pe.y),le.push(F.x,F.y)}if(q){const xe=D[te],pe=D[I],F=D[ce];he.push(xe.x,xe.y),he.push(pe.x,pe.y),he.push(F.x,F.y)}}for(;Oe&&Ce<t;){Ce++,Oe=!1,U=Z,Z=[],N&&(V=W,W=[]),B&&(P=$,$=[]),k&&(O=le,le=[]),q&&(H=he,he=[]);for(let te=0,I=0,ce=U.length;te<ce;te+=9,I+=6){i.fromArray(U,te+0),r.fromArray(U,te+3),o.fromArray(U,te+6),N&&(c.fromArray(V,te+0),h.fromArray(V,te+3),u.fromArray(V,te+6)),B&&(g.fromArray(P,te+0),x.fromArray(P,te+3),p.fromArray(P,te+6)),k&&(v.fromArray(O,I+0),M.fromArray(O,I+2),S.fromArray(O,I+4)),q&&(z.fromArray(H,I+0),T.fromArray(H,I+2),y.fromArray(H,I+4));const ae=i.distanceToSquared(r),se=r.distanceToSquared(o),de=i.distanceToSquared(o);ae>n||se>n||de>n?(Oe=!0,ae>=se&&ae>=de?(a.lerpVectors(i,r,.5),N&&d.lerpVectors(c,h,.5),B&&m.lerpColors(g,x,.5),k&&E.lerpVectors(v,M,.5),q&&b.lerpVectors(z,T,.5),Ie(0,3,2),Ie(3,1,2)):se>=ae&&se>=de?(a.lerpVectors(r,o,.5),N&&d.lerpVectors(h,u,.5),B&&m.lerpColors(x,p,.5),k&&E.lerpVectors(M,S,.5),q&&b.lerpVectors(T,y,.5),Ie(0,1,3),Ie(3,2,0)):(a.lerpVectors(i,o,.5),N&&d.lerpVectors(c,u,.5),B&&m.lerpColors(g,p,.5),k&&E.lerpVectors(v,S,.5),q&&b.lerpVectors(z,y,.5),Ie(0,1,3),Ie(3,1,2))):Ie(0,1,2)}}const ze=new je;return ze.setAttribute("position",new Ae(Z,3)),N&&ze.setAttribute("normal",new Ae(W,3)),B&&ze.setAttribute("color",new Ae($,3)),k&&ze.setAttribute("uv",new Ae(le,2)),q&&ze.setAttribute("uv1",new Ae(he,2)),ze}}function ih(s){const e=[];for(let a=0;a<4;a++){const l=a*Math.PI/2,c=Math.cos(l+Math.PI/4)>0?.64:-.64,h=Math.sin(l+Math.PI/4)>0?.64:-.64;for(let u=0;u<=4;u++){const d=l+u*Math.PI/8;e.push([c+.36*Math.cos(d),h+.36*Math.sin(d)])}}const t=e.length,n=[],i=[];for(const a of s)for(const[l,c]of e)n.push((a.x??0)+l*a.w,a.y,(a.z??0)+c*a.d);for(let a=0;a<s.length-1;a++)for(let l=0;l<t;l++){const c=a*t+l,h=a*t+(l+1)%t,u=c+t,d=h+t;i.push(c,u,h,h,u,d)}for(let a=1;a<t-1;a++){i.push(0,a,a+1);const l=(s.length-1)*t;i.push(l,l+a+1,l+a)}const r=new je;r.setAttribute("position",new Ae(n,3)),r.setIndex(i),r.computeVertexNormals();const o=ka(r,.5);return r.dispose(),o}class lu{batches=new Map;finishes;constructor(e){const t=(n,i,r)=>new Ke({color:n,roughness:i,metalness:r,envMap:e.hull.envMap,envMapIntensity:.85});this.finishes={gold:t(11836e3,.39,.68),edge:t(14732179,.31,.7),bronze:t(7823420,.44,.65),dark:t(1515563,.47,.45),steel:t(7633284,.32,.76),blue:new $h({color:1392482,emissive:413557,emissiveIntensity:.4,roughness:.23,metalness:.38,clearcoat:.7,clearcoatRoughness:.18}),glow:new Ge({color:5888762,toneMapped:!1})}}add(e,t,n=[0,0,0],i=[0,0,0],r=[1,1,1]){const o=e.index?e.toNonIndexed():e.clone();e.dispose(),o.deleteAttribute("uv"),o.applyMatrix4(new Fe().compose(new w(...n),new Pt().setFromEuler(new Yt(...i)),new w(...r)));const a=this.batches.get(t)??[];a.push(o),this.batches.set(t,a)}loft(e,t,n=[0,0,0],i=[0,0,0]){this.add(ih(e),t,n,i)}shell(e,t,n=[0,0,-1],i=36,r=32){const o=new hn(e.map(d=>new w(...d.p)),!1,"centripetal"),a=new hn(e.map((d,f)=>new w(d.w,d.d,f)),!1,"catmullrom",.35),l=[],c=[];for(let d=0;d<=i;d++){const f=d/i,g=o.getPoint(f),x=o.getTangent(f).normalize(),p=a.getPoint(f);let m=new w(...n);Math.abs(m.dot(x))>.97&&(m=new w(1,0,0));const _=m.clone().cross(x).normalize();m=x.clone().cross(_).normalize();for(let v=0;v<r;v++){const M=v/r*Math.PI*2,S=Math.cos(M),E=Math.sin(M),C=Math.sign(S)*Math.pow(Math.abs(S),.83),z=Math.sign(E)*Math.pow(Math.abs(E),.83),T=g.clone().addScaledVector(_,C*Math.max(.005,p.x)).addScaledVector(m,z*Math.max(.005,p.y));l.push(T.x,T.y,T.z)}}for(let d=0;d<i;d++)for(let f=0;f<r;f++){const g=d*r+f,x=d*r+(f+1)%r;c.push(g,x,g+r,x,x+r,g+r)}const h=l.length/3;l.push(...e[0].p,...e[e.length-1].p);for(let d=0;d<r;d++)c.push(h,(d+1)%r,d),c.push(h+1,i*r+d,i*r+(d+1)%r);const u=new je;u.setAttribute("position",new Ae(l,3)),u.setIndex(c),u.computeVertexNormals(),this.add(u,t)}curvedPlate(e,t,n,i,r=[0,0,0],o=.07,a=[0,0,0]){const l=e.map(x=>new w(x[0],x[1],0)),c=new hn(l,!0,"centripetal"),h=new De(c.getPoints(e.length*5).map(x=>new Q(x.x,x.y))),u=new xt(h,{depth:t,steps:1,bevelEnabled:!0,bevelThickness:o,bevelSize:o,bevelSegments:3,curveSegments:1});u.translate(0,0,-t/2);const d=new Dx(.44,5).modify(u);u.dispose();const f=d.getAttribute("position");for(let x=0;x<f.count;x++){const p=f.getX(x),m=f.getY(x);f.setZ(x,f.getZ(x)+a[0]*p*p+a[1]*m*m+a[2]*m)}d.computeVertexNormals();const g=ka(d,.72);d.dispose(),this.add(g,n,i,r)}plate(e,t,n,i=[0,0,0],r=[0,0,0],o=.06){const a=new De(e.map(h=>new Q(...h)));a.closePath();const l=new xt(a,{depth:t,steps:1,bevelEnabled:o>0,bevelThickness:o,bevelSize:o,bevelSegments:3,curveSegments:1});l.translate(0,0,-t/2);const c=ka(l,.5);l.dispose(),this.add(c,n,i,r)}block(e,t,n,i=[0,0,0],r=.04){const[o,a,l]=t,c=Math.min(o,a)*.12;this.plate([[-o/2+c,-a/2],[o/2-c,-a/2],[o/2,-a/2+c],[o/2,a/2-c],[o/2-c,a/2],[-o/2+c,a/2],[-o/2,a/2-c],[-o/2,-a/2+c]],l,n,e,i,r)}strut(e,t,n,i,r,o,a){const l=new w(...e),c=new w(...t),h=c.clone().sub(l),u=h.length(),d=ih([{y:0,w:n*.85,d:r*.85},{y:Math.min(.12,u*.08),w:n,d:r},{y:u-Math.min(.12,u*.08),w:i,d:o},{y:u,w:i*.85,d:o*.85}]);d.applyQuaternion(new Pt().setFromUnitVectors(new w(0,1,0),h.normalize())),d.translate(...e),this.add(d,a)}drum(e,t,n,i,r=[Math.PI/2,0,0],o=[1,1,1]){this.add(new et(t,t,n,16,1),i,e,r,o)}ring(e,t,n,i,r=[0,0,0],o=[1,1,1],a=Math.PI*2){this.add(new at(t,n,4,32,a),i,e,r,o)}line(e,t,n){for(let i=1;i<e.length;i++){const r=new w(...e[i-1]),o=new w(...e[i]),a=o.clone().sub(r),l=new lt(t*2,a.length(),t*.9);l.applyQuaternion(new Pt().setFromUnitVectors(new w(0,1,0),a.normalize()));const c=r.add(o).multiplyScalar(.5);l.translate(c.x,c.y,c.z),this.add(l,n)}}surfaceLine(e,t,n,i,r,o,a){const l=new hn(e.map(([u,d])=>new w(u,d,0))),c=new Yt(...n),h=new w(...t);this.line(l.getPoints(16).map(u=>(u.z=r+i[0]*u.x*u.x+i[1]*u.y*u.y+i[2]*u.y,u.applyEuler(c).add(h),[u.x,u.y,u.z])),o,a)}leanAbove(e,t){for(const n of this.batches.values())for(const i of n){const r=i.getAttribute("position"),o=i.getAttribute("normal");for(let a=0;a<r.count;a++)if(r.getY(a)>e){r.setZ(a,r.getZ(a)-t*(r.getY(a)-e));const l=new w(o.getX(a),o.getY(a)+t*o.getZ(a),o.getZ(a)).normalize();o.setXYZ(a,l.x,l.y,l.z)}}}finish(e,t,n,i,r,o,a=1/0){const l=new qe;l.name="protoss-"+e,Object.assign(l.userData,{unitKind:e,label:t,forward:"-Z",ownsResources:!0});for(const[_,v]of this.batches){const M=cs(v,!1);if(v.forEach(E=>E.dispose()),!M)throw new Error("Heavy geometry merge failed: "+e);const S=new ve(M,this.finishes[_]);S.name=e+"-"+_,S.castShadow=!0,S.receiveShadow=!0,l.add(S)}for(const _ of Object.keys(this.finishes))this.batches.has(_)||this.finishes[_].dispose();const c=new Lt().setFromObject(l),h=c.getSize(new w),u=Math.min(1,i/h.x),d=n/h.y,f=Math.min(1,r/h.z),g=new Fe().makeScale(u,d,f);g.setPosition(-(c.max.x+c.min.x)*u/2,-c.min.y*d,-(c.max.z+c.min.z)*f/2);let x=0,p=0;for(const _ of l.children){const v=_.geometry;v.applyMatrix4(g);const M=v.getAttribute("position");for(let S=0;S<M.count;S++){const E=Math.hypot(M.getX(S),M.getZ(S));x=Math.max(x,E),M.getY(S)<.6&&(p=Math.max(p,E))}}const m=Math.min(1,(a-1e-4)/x,(o-1e-4)/p);for(const _ of l.children){const v=_.geometry;v.scale(m,1,m),v.computeBoundingBox(),v.computeBoundingSphere()}return l}}const xn=[[0,-1],[-.7,-.62],[-1,.2],[-.66,.84],[0,1],[.66,.84],[1,.2],[.7,-.62]],ln=(s,e,t)=>s.map(([n,i])=>[n*e,i*t]),mi=(s,e)=>s.map(([t,n])=>[t*e,n]);function Ix(s){const e=new lu(s);e.shell([{p:[0,2.35,.2],w:.92,d:.65},{p:[0,3.1,.25],w:1.4,d:.92},{p:[0,3.72,.3],w:1.3,d:.8}],"dark"),e.shell([{p:[0,3.36,.08],w:.85,d:.6},{p:[0,4.38,.25],w:1.68,d:1.03},{p:[0,5.46,.49],w:1.48,d:1.01},{p:[0,6.26,.62],w:.81,d:.65},{p:[0,6.58,.57],w:.2,d:.2}],"bronze");for(let n=0;n<5;n++){const i=2.75+n*.19;e.curvedPlate([[-.87,-.045],[.87,-.045],[.95,.055],[-.95,.055]],.1,"bronze",[0,i,-.94],[0,0,0],.025,[.19,0,0])}for(const n of[-1,1]){e.shell([{p:[n*.75,4.7,.25],w:.63,d:.46},{p:[n*1.55,5.18,.28],w:.65,d:.53},{p:[n*2.14,5.15,.15],w:.47,d:.38}],"dark",[0,0,-1],20,24);for(let o=0;o<3;o++)e.curvedPlate(mi([[-.57,-.13],[.43,-.23],[.65,.12],[.13,.35],[-.52,.2]],n),.16,"gold",[n*1.55,5.6-o*.3,-.55-o*.07],[.13,n*.25,n*.12],.055,[.12,.22,.09]);e.shell([{p:[n*2.13,5.08,1.15],w:.24,d:.36},{p:[n*2.42,5.26,.64],w:.79,d:.92},{p:[n*2.53,5.23,-.28],w:.93,d:.93},{p:[n*2.67,5.08,-1.34],w:.7,d:.81},{p:[n*2.63,4.97,-2.06],w:.36,d:.54}],"bronze",[0,1,0],40,36),e.curvedPlate([[-.63,-1.1],[.52,-1.12],[.89,-.38],[.84,.6],[.32,1.35],[-.25,1.48],[-.87,.68],[-.99,-.18]],.27,"gold",[n*2.48,6.23,-.22],[-Math.PI/2,0,n*.1],.095,[-.38,-.24,-.04]),e.surfaceLine([[-.7,-.43],[-.53,.03],[-.3,.53],[.16,1.02]],[n*2.48,6.23,-.22],[-Math.PI/2,0,n*.1],[-.38,-.24,-.04],.24,.019,"dark"),e.curvedPlate(ln(xn,.24,.38),.055,"dark",[n*2.45,6.39,-.3],[-Math.PI/2,0,0],.025,[-.3,-.2,0]),e.curvedPlate(ln(xn,.16,.29),.05,"blue",[n*2.45,6.43,-.3],[-Math.PI/2,0,0],.018,[-.3,-.2,0]);const i=[[-1.14,-.02],[-.72,.64],[.45,.85],[1.78,.22],[1.95,-.47],[1.13,-.85],[-.62,-.76]],r=[0,n*Math.PI/2,0];e.curvedPlate(i.map(([o,a])=>[o*n,a]),.27,"gold",[n*3.22,5.13,-.09],r,.075,[-.24,-.37,0]),e.curvedPlate([[-.59,-.38],[.26,-.34],[1.2,-.63],[.87,-.76],[-.36,-.64]].map(([o,a])=>[o*n,a]),.07,"blue",[n*3.41,5.12,-.1],r,.035,[-.24,-.37,0]),e.curvedPlate(ln(xn,.43,.61),.105,"dark",[n*3.3,5.49,.46],r,.035,[-.32,-.34,0]),e.curvedPlate(ln(xn,.34,.51),.07,"blue",[n*3.4,5.49,.46],r,.035,[-.32,-.34,0]),e.curvedPlate([[-.39,-.65],[.4,-.65],[.48,.3],[.28,.7],[-.27,.7],[-.48,.3]],.27,"gold",[n*2.63,5.02,-2.08],[0,n*.07,0],.065,[.21,.08,0]);for(const o of[4.77,5.3])e.block([n*2.63,o,-2.33],[.47,.37,.52],"bronze",[0,0,0],.075),e.block([n*2.63,o,-2.62],[.5,.38,.2],"edge",[0,0,0],.055),e.block([n*2.63,o,-2.758],[.33,.235,.035],"dark",[0,0,0],.026),e.block([n*2.63,o,-2.783],[.225,.12,.014],"blue",[0,0,0],.018),e.block([n*2.63,o+.1,-2.3],[.29,.045,.34],"steel",[0,0,0],.016);e.curvedPlate(mi([[.08,-1.03],[.76,-.87],[1.2,-.14],[1.17,.76],[.48,1.45],[.04,1.05],[.28,.23]],n),.23,"gold",[n*.25,4.76,-.84],[0,0,0],.085,[.2,.045,.35]);for(const o of[-1,1]){const a=[n*1.22,3.12,o*.9],l=[n*2.76,2.15,o*2.08],c=[n*3.12,.67,o*2.86];e.drum(a,.48,.62,"dark",[0,0,Math.PI/2]),e.shell([{p:[n*1.35,3.1,o*1],w:.37,d:.33},{p:[n*1.94,3.02,o*1.5],w:.59,d:.45},{p:[n*2.48,2.59,o*1.92],w:.56,d:.4},{p:[n*2.69,2.31,o*2.03],w:.34,d:.28}],"gold",[0,0,-o],28,28),e.shell([{p:[n*1.51,3.4,o*1.2],w:.16,d:.095},{p:[n*2.07,3.25,o*1.66],w:.37,d:.115},{p:[n*2.57,2.64,o*2.11],w:.24,d:.08}],"edge",[0,0,-o],24,20),e.drum(l,.43,.64,"dark",[0,0,Math.PI/2]),e.drum([n*3.13,2.15,o*2.08],.31,.13,"bronze",[0,0,Math.PI/2]),e.ring([n*3.23,2.15,o*2.08],.235,.045,"edge",[0,Math.PI/2,0]),e.drum([n*3.25,2.15,o*2.08],.13,.07,"steel",[0,0,Math.PI/2]),e.shell([{p:[n*2.82,2.04,o*2.16],w:.35,d:.3},{p:[n*3.06,1.53,o*2.53],w:.47,d:.36},{p:[n*3.15,.98,o*2.77],w:.33,d:.26},{p:[n*3.12,.76,o*2.84],w:.22,d:.2}],"gold",[0,0,-o],28,28);const h=[o<0?-.25:.25,o<0?0:Math.PI,n*-.08];e.curvedPlate([[0,.79],[-.43,.14],[-.35,-.29],[.31,-.38],[.46,.16]],.17,"edge",[n*2.87,2.05,o*2.43],h,.055,[.42,.16,0]);for(const u of[-.11,.11])e.surfaceLine([[u,.35],[u*.85,.21],[u*.7,.1]],[n*2.87,2.05,o*2.43],h,[.42,.16,0],-.149,.014,"dark");e.curvedPlate([[-.2,.44],[.19,.44],[.23,-.12],[.03,-.5],[-.18,-.27]],.075,"blue",[n*3.13,1.35,o*2.9],h,.028,[.4,.18,0]),e.drum(c,.245,.48,"dark",[0,0,Math.PI/2]),e.shell([{p:[n*3.12,.61,o*2.9],w:.22,d:.16},{p:[n*3.18,.36,o*3.21],w:.31,d:.19},{p:[n*3.19,.14,o*3.54],w:.19,d:.1},{p:[n*3.18,.055,o*3.83],w:.014,d:.018}],"edge",[0,1,0],24,24),e.shell([{p:[n*3.2,.43,o*3.24],w:.07,d:.035},{p:[n*3.2,.23,o*3.53],w:.063,d:.025},{p:[n*3.18,.095,o*3.77],w:.009,d:.012}],"bronze",[0,1,0],16,16)}}const t=[.21,.055,.38];e.curvedPlate([[0,-1.34],[-.52,-.91],[-.69,.14],[-.48,1.04],[0,1.6],[.48,1.04],[.69,.14],[.52,-.91]],.2,"dark",[0,4.91,-1],[0,0,0],.055,t),e.curvedPlate([[0,-1.17],[-.38,-.81],[-.48,.15],[-.3,1.02],[0,1.35],[.3,1.02],[.48,.15],[.38,-.81]],.08,"blue",[0,4.91,-1.28],[0,0,0],.025,t);for(const n of[-1,1])e.curvedPlate(mi([[.015,-1.43],[.37,-.97],[.71,-.11],[.66,.67],[.25,1.44],[.02,1.68],[.11,1.12],[.4,.46],[.43,-.16],[.18,-.94]],n),.21,"gold",[0,4.91,-1.27],[0,0,0],.055,t);e.curvedPlate([[0,-1.08],[-.1,-.63],[-.11,.92],[0,1.47],[.11,.92],[.1,-.63]],.14,"edge",[0,4.91,-1.37],[0,0,0],.028,t);for(let n=0;n<4;n++)for(const i of[-1,1]){const r=4.18+n*.31,o=r-4.91;e.curvedPlate([[-.12,-.037],[.12,-.037],[.13,.039],[-.13,.039]],.045,"bronze",[i*.29,r,-1.28+.055*o*o+.38*o],[0,0,i*.17],.013,[.2,0,0])}return e.block([0,5.83,-1.1],[.27,.055,.07],"glow",[.35,0,0],.014),e.curvedPlate([[0,-.68],[-.67,-.15],[-.89,.43],[0,.28],[.89,.43],[.67,-.15]],.22,"gold",[0,2.39,-1.1],[0,0,0],.075,[.2,.07,.11]),e.curvedPlate([[0,-.46],[-.48,-.03],[-.58,.2],[0,.1],[.58,.2],[.48,-.03]],.07,"blue",[0,2.39,-1.29],[0,0,0],.035,[.2,.07,.11]),e.finish("immortal","不朽者 · IMMORTAL",6.8,8,8,5.7)}function Lx(s){const e=new lu(s);e.shell([{p:[0,12.1,.65],w:.87,d:.77},{p:[0,14,.46],w:2.21,d:1.65},{p:[0,17.15,-.1],w:3.32,d:2.36},{p:[0,20.2,-.74],w:3.14,d:2.22},{p:[0,22.22,-1.1],w:2.13,d:1.57},{p:[0,23.18,-1.08],w:.61,d:.47}],"bronze",[0,0,-1],48,40);for(let i=0;i<4;i++){const r=15.15+i*1.65,o=i===3?1.76:2.65;e.curvedPlate([[-o,-.51],[-o*.7,-.89],[o*.7,-.89],[o,-.51],[o*.82,.64],[0,.95],[-o*.82,.64]],.26,"gold",[0,r,1.93-i*.28],[.12,0,0],.12,[-.17,-.13,0])}e.shell([{p:[0,10.42,.44],w:.8,d:.67},{p:[0,11.9,.59],w:1.09,d:.83},{p:[0,14.1,.24],w:1.61,d:1.2}],"dark",[0,0,-1],24,28);for(let i=0;i<7;i++){const r=10.8+i*.43,o=.89+i*.105,a=.7+i*.063;e.shell([{p:[0,r,.49-i*.035],w:o*.89,d:a*.91},{p:[0,r+.15,.49-i*.035],w:o,d:a},{p:[0,r+.28,.49-i*.035],w:o*.94,d:a*.96}],i%2===0?"gold":"bronze",[0,0,-1],8,28),e.curvedPlate([[-o,.09],[0,-.3],[o,.09],[o*.65,-.22],[0,-.51],[-o*.65,-.22]],.1,"edge",[0,r+.1,-.28-i*.095],[0,0,0],.035,[.2,0,0])}const t=[.28,.032,-.27],n=[[-.62,-1.76],[-.95,-.81],[-.85,.58],[-.5,1.64],[.05,1.9],[.78,1.04],[.74,-.55],[.35,-1.76],[-.07,-2.13]];for(const i of[-1,1]){const r=[0,i*.055,i*-.1];e.curvedPlate(mi([[-.61,-2.78],[-1.22,-1.64],[-1.26,.77],[-.74,2.72],[.07,3.88],[.89,2.56],[1.2,.62],[1.12,-1.25],[.58,-2.77],[.02,-3.22]],i),.42,"gold",[i*1.44,17.6,-2.41],r,.14,t),e.surfaceLine(mi([[-.62,2],[-.38,2.41],[0,2.66],[.31,2.75]],i),[i*1.44,17.6,-2.41],r,t,-.362,.026,"dark"),e.curvedPlate(mi(ln(n,1.12,1.08),i),.15,"dark",[i*1.41,17.45,-2.64],r,.075,t),e.curvedPlate(mi(n,i),.13,"blue",[i*1.41,17.45,-2.76],r,.075,t),e.shell([{p:[i*.77,15.02,-2.1],w:.09,d:.1},{p:[i*.55,16.4,-2.62],w:.2,d:.13},{p:[i*.59,18.05,-2.96],w:.17,d:.12},{p:[i*.98,19.28,-3.04],w:.07,d:.06}],"edge",[0,0,-1],28,20);const o=(h,u)=>[i*(1.41+h),17.45+u,-2.93+.28*h*h+.032*u*u-.27*u];e.line([o(-.25,-1.2),o(-.37,-.6),o(-.38,-.13),o(-.1,.19),o(-.08,.82),o(.19,1.21)],.024,"glow"),e.line([o(.24,-1.38),o(.31,-.75),o(.17,-.22),o(.29,.31),o(.35,.72)],.018,"glow");const a=[0,i*Math.PI/2,0],l=[-.25,-.105,-.025];e.curvedPlate(ln(xn,1.43,2.29),.22,"gold",[i*3.22,18.37,-.12],a,.11,l),e.curvedPlate(ln(xn,1.19,1.99),.14,"dark",[i*3.39,18.37,-.12],a,.055,l),e.curvedPlate(ln(xn,1.05,1.84),.085,"blue",[i*3.52,18.37,-.12],a,.045,l);const c=[];for(let h=0;h<=24;h++){const u=h/24*Math.PI*1.65,d=Math.cos(u)*.61,f=Math.sin(u)*1.11;c.push([i*(3.61-.25*d*d-.105*f*f-.025*f),18.37+f,-.12-d])}e.line(c,.026,"glow"),e.shell([{p:[i*2.28,19.78,-.02],w:.54,d:.43},{p:[i*2.28,21.05,-.39],w:.9,d:.65},{p:[i*1.98,22.41,-.96],w:.55,d:.43},{p:[i*1.58,23.76,-1.19],w:.025,d:.018}],"gold",[0,0,-1],32,28),e.curvedPlate(ln(xn,.64,.84),.2,"bronze",[i*2.75,20.52,-1.02],[0,i*.84,i*.05],.075,[.14,.15,0]),e.curvedPlate(ln(xn,.43,.57),.095,"blue",[i*2.94,20.53,-1.19],[0,i*.84,i*.05],.045,[.14,.15,0]),e.ring([i*3.01,20.55,-1.37],.26,.028,"glow",[0,i*.84,0],[1,1.17,1]),e.shell([{p:[i*2.53,16.6,-.69],w:.29,d:.3},{p:[i*3.27,17.1,-1.25],w:.61,d:.55},{p:[i*3.76,16.32,-1.98],w:.59,d:.5},{p:[i*3.56,15.33,-2.52],w:.26,d:.27}],"gold",[0,0,-1],32,28),e.curvedPlate([[-.25,-.62],[-.47,.08],[-.31,.71],[.21,.82],[.47,.28],[.31,-.52]],.08,"blue",[i*3.47,16.39,-2.4],[-.33,i*.15,i*.23],.055,[.25,.13,.04]),e.shell([{p:[i*3.57,15.58,-2.51],w:.28,d:.21},{p:[i*3.58,15.13,-2.81],w:.27,d:.19}],"bronze",[0,0,-1],12,20);for(const[h,u]of[[-.18,.12],[.18,.12],[0,-.18]])e.drum([i*3.58+h,15.19+u,-2.9],.14,.2,"dark"),e.ring([i*3.58+h,15.19+u,-3.018],.115,.031,"edge"),e.drum([i*3.58+h,15.19+u,-3.06],.075,.025,"glow");e.shell([{p:[i*3,17.52,.17],w:.22,d:.16},{p:[i*3.78,18.16,-.1],w:.31,d:.14},{p:[i*4.91,18.73,-.68],w:.012,d:.016}],"edge",[0,0,-1],24,20);for(const h of[-1,1]){const u=h<0?10.6:11.18,d=[i*1.03,10.63,h*1.02],f=[i*5.31,u,h*3.03],g=[i*4.13,4.69,h*3.86],x=[i*5.39,.73,h*3.72];e.drum(d,.51,.66,"dark",[0,0,Math.PI/2]),e.drum([i*1.4,10.63,h*1.02],.3,.12,"bronze",[0,0,Math.PI/2]),e.shell([{p:[i*1.42,10.65,h*1.13],w:.27,d:.25},{p:[i*2.95,10.16,h*1.97],w:.49,d:.3},{p:[i*4.45,u-.22,h*2.77],w:.39,d:.25},{p:[i*5,u,h*2.97],w:.23,d:.2}],"gold",[0,0,-h],28,24),e.strut([i*1.8,10.29,h*1.39],[i*4.75,u-.35,h*2.91],.1,.11,.085,.07,"steel"),e.drum(f,.55,.73,"dark",[0,0,Math.PI/2]),e.shell([{p:[i*5.3,u-.63,h*3.19],w:.2,d:.18},{p:[i*5.33,u+.06,h*3.3],w:.68,d:.4},{p:[i*5.17,u+.73,h*3.13],w:.47,d:.29},{p:[i*5.1,u+1.73,h*2.93],w:.014,d:.02}],"gold",[0,0,-h],28,28);const p=[h<0?-.11:.11,h<0?0:Math.PI,i*-.11];e.curvedPlate(ln(xn,.48,.51),.075,"dark",[i*5.32,u+.06,h*3.63],p,.045,[.38,.27,0]),e.curvedPlate(ln(xn,.35,.38),.065,"blue",[i*5.32,u+.06,h*3.73],p,.032,[.38,.27,0]),e.ring([i*5.32,u+.06,h*3.81],.21,.022,"glow",[0,0,0],[1,.9,1],Math.PI*1.6),e.shell([{p:[i*5.26,u-.43,h*3.03],w:.32,d:.27},{p:[i*5.13,8.18,h*3.47],w:.43,d:.29},{p:[i*4.6,6.1,h*3.84],w:.27,d:.18},{p:[i*4.17,5.04,h*3.86],w:.18,d:.15}],"gold",[0,0,-h],36,24),e.shell([{p:[i*5.17,u-.65,h*3.29],w:.13,d:.07},{p:[i*5.05,8.06,h*3.76],w:.15,d:.065},{p:[i*4.25,5.14,h*4.04],w:.052,d:.035}],"bronze",[0,0,-h],28,16),e.drum(g,.29,.51,"dark",[0,0,Math.PI/2]),e.drum([i*4.42,4.69,h*3.86],.18,.1,"steel",[0,0,Math.PI/2]),e.shell([{p:[i*4.15,4.36,h*3.86],w:.18,d:.16},{p:[i*4.59,3.08,h*3.76],w:.3,d:.15},{p:[i*5.2,1.46,h*3.68],w:.17,d:.1},{p:[i*5.36,.99,h*3.7],w:.1,d:.08}],"edge",[0,0,-h],28,24),e.drum(x,.19,.35,"dark",[0,0,Math.PI/2]),e.shell([{p:[i*5.4,.62,h*3.74],w:.15,d:.12},{p:[i*5.46,.34,h*4.01],w:.21,d:.11},{p:[i*5.43,.06,h*4.4],w:.014,d:.02}],"bronze",[0,1,0],20,20)}}e.shell([{p:[0,19.47,-2.99],w:.26,d:.23},{p:[0,20.81,-2.95],w:1.24,d:.45},{p:[0,22.18,-2.57],w:1.12,d:.41},{p:[0,23.26,-1.74],w:.13,d:.12}],"gold",[0,0,-1],32,28),e.shell([{p:[0,14.07,-1.94],w:.075,d:.09},{p:[0,16.06,-2.61],w:.29,d:.2},{p:[0,18.45,-3.03],w:.19,d:.17},{p:[0,20.01,-2.85],w:.035,d:.05}],"edge",[0,0,-1],32,20),e.curvedPlate([[0,-.54],[-.67,.03],[-.72,.36],[0,.18],[.72,.36],[.67,.03]],.21,"gold",[0,14.34,-1.95],[0,0,0],.075,[.19,.04,0]),e.shell([{p:[0,13.73,1.26],w:.17,d:.14},{p:[0,16.66,3.32],w:.37,d:.29},{p:[0,19.7,4.12],w:.43,d:.31},{p:[0,22.45,3.17],w:.37,d:.26},{p:[0,23.34,1.44],w:.075,d:.1}],"gold",[1,0,0],40,24);for(let i=0;i<4;i++)e.block([0,16.85+i*1.4,3.63+Math.sin(i)*.3],[.61,.1,.16],"bronze",[.15,0,0],.018);return e.leanAbove(12,.085),e.finish("colossus","巨像 · COLOSSUS",24,13.6,13.6,7.1,7.35)}const vn=s=>new w(...s),sh=new w(0,1,0);function Nx(s,e,t){const n=[],i=[],r=[];for(let c=0;c<=16;c++){const h=c/16,u=Math.pow(Math.max(1e-4,Math.sin(Math.PI*h)),.65);for(let d=0;d<=16;d++){const f=Math.PI*d/16,g=Math.pow(Math.sin(f),5)*.16;if(n.push(Math.cos(f)*s*u,(Math.sin(f)+g)*e*u,(h-.5)*t),i.push(d/16,h),c<16&&d<16){const x=c*17+d,p=x+16+1;r.push(x,x+1,p,p,x+1,p+1)}}}const l=new je;return l.setAttribute("position",new Ae(n,3)),l.setAttribute("uv",new Ae(i,2)),l.setIndex(r),l.computeVertexNormals(),l}class rh{constructor(e,t,n,i,r){this.root=e,this.collision=t,this.x=n,this.z=i,this.palette=r}batches=new Map;add(e,t,n=[0,0,0],i=[0,0,0],r=[1,1,1],o=!1){e.applyMatrix4(new Fe().compose(new w(this.x+n[0],n[1],this.z+n[2]),new Pt().setFromEuler(new Yt(...i)),vn(r))),o&&!t.transparent&&this.collision.addStaticGeometry(e,new Fe,{tag:"foundry-prop",owner:"foundry-bay-"+this.x+"-"+this.z,part:e.type+"@"+n.join(",")});const a=e.index?e.toNonIndexed():e;a!==e&&e.dispose(),a.deleteAttribute("uv");const l=this.batches.get(t)??[];l.push(a),this.batches.set(t,l)}sphere(e,t,n,i=!1){this.add(new ft(1,20,12),n,e,[0,0,0],t,i)}cylinder(e,t,n,i,r,o=!1){o&&t===n&&!r.transparent&&this.collision.addCylinder(new w(this.x+e[0],e[1],this.z+e[2]),t,i,{tag:"foundry-prop",owner:"foundry-bay-"+this.x+"-"+this.z,part:"cylinder@"+e.join(",")}),this.add(new et(t,n,i,40),r,e,[0,0,0],[1,1,1],o&&t!==n)}rod(e,t,n,i,r=n,o=!0){const a=vn(e),l=vn(t),c=l.clone().sub(a),h=new et(r,n,c.length(),12);h.applyQuaternion(new Pt().setFromUnitVectors(sh,c.clone().normalize())),this.add(h,i,a.add(l).multiplyScalar(.5).toArray(),[0,0,0],[1,1,1],o)}tube(e,t,n){this.add(new Si(new hn(e.map(vn)),36,t,8,!1),n)}ring(e,t,n,i,r=[Math.PI/2,0,0],o=Math.PI*2){this.add(new at(t,n,6,t<1.5?24:64,o),i,e,r)}plate(e,t,n,i=[0,0,0]){this.add(Nx(...t),n,e,i)}armor(e,t,n,i,r=.65){const o=vn(t).sub(vn(e)),a=o.length(),l=[[.15,0],[.68,.12],[1,.3],[.92,.53],[.56,.84],[.08,1]],c=new jr(l.map(([h,u])=>new Q(h*n,u*a)),12);c.scale(1,1,r),c.applyQuaternion(new Pt().setFromUnitVectors(sh,o.normalize())),this.add(c,i,e)}panel(e,t,n,i,r,o=[0,0,0]){const a=new De;a.moveTo(0,n*.56),a.lineTo(t*.5,n*.24),a.lineTo(t*.39,-n*.28),a.lineTo(0,-n*.55),a.lineTo(-t*.39,-n*.28),a.lineTo(-t*.5,n*.24),a.closePath();const l=new xt(a,{depth:i,bevelEnabled:!0,bevelSegments:1,steps:1,bevelSize:Math.min(t*.08,.06),bevelThickness:.035});l.translate(0,0,-i/2),this.add(l,r,e,o,[1,1,1],!0)}piston(e,t,n=.1){const i=vn(e),r=vn(t),o=i.clone().lerp(r,.6);this.rod(e,o.toArray(),n*1.55,this.palette.dark),this.rod(o.toArray(),t,n,this.palette.steel);for(const a of[.1,.48,.59]){const l=i.clone().lerp(r,a),c=i.clone().lerp(r,a+.035);this.rod(l.toArray(),c.toArray(),n*1.85,this.palette.gold)}}joint(e,t,n=[1,0,0]){const i=new Pt().setFromUnitVectors(new w(0,0,1),vn(n).normalize()),r=(o,a)=>{o.applyQuaternion(i),this.add(o,a,e)};r(new et(t,t,t*.7,12).rotateX(Math.PI/2),this.palette.dark);for(const o of[-1,1]){r(new at(t*.8,t*.075,5,24).translate(0,0,o*t*.39),this.palette.gold),r(new et(t*.4,t*.4,.055,6).rotateX(Math.PI/2).translate(0,0,o*t*.43),this.palette.steel);for(let a=0;a<8;a++){const l=a*Math.PI/4;r(new et(.045,.045,.05,6).rotateX(Math.PI/2).translate(Math.cos(l)*t*.63,Math.sin(l)*t*.63,o*t*.43),this.palette.steel)}}for(let o=0;o<12;o++){const a=o*Math.PI/6;r(new lt(t*.18,t*.23,t*.52).translate(0,t*.94,0).rotateZ(a),this.palette.steel)}}gem(e,t,n=1.5){this.add(new qt(t),this.palette.crystal,e,[0,0,0],[.65,n,.55]);for(const i of[-1,1])this.panel([e[0]+i*t*.5,e[1],e[2]+.03],t*.2,t*n*1.8,.07,this.palette.gold,[0,0,-i*.13])}finish(e){for(const[t,n]of this.batches){const i=cs(n,!1);for(const o of n)o.dispose();if(!i)throw new Error("Incompatible foundry geometry: "+e);i.computeBoundingSphere();const r=new ve(i,t);r.name=e+"-"+t.name,r.castShadow=!(t instanceof Ge),r.receiveShadow=!0,r.matrixAutoUpdate=!1,this.root.add(r)}this.batches.clear()}}function Ux(s,e,t){const n=s.palette;s.cylinder([0,.22,0],e-.08,e,.44,n.dark,!0),s.cylinder([0,.48,0],e-.28,e-.1,.12,n.steel,!0),s.cylinder([0,.56,0],e-.52,e-.35,.08,n.dark,!0),s.ring([0,.4,0],e-.08,.075,t),s.ring([0,.62,0],e-.75,.045,t),s.ring([0,.615,0],e-1.05,.022,n.gold),s.ring([0,.616,0],1.6,.025,t);for(let i=0;i<16;i++){const r=i*Math.PI/8,o=Math.PI/8-.065,a=new De;a.absarc(0,0,e-.13,r,r+o,!1),a.absarc(0,0,e-.54,r+o,r,!0),a.closePath();const l=new xt(a,{depth:.12,bevelEnabled:!0,bevelSegments:1,bevelSize:.025,bevelThickness:.02,steps:1,curveSegments:4});l.rotateX(-Math.PI/2),s.add(l,i%4===0?n.gold:n.steel,[0,.55,0],[0,0,0],[1,1,1],!0);const c=r+o/2,h=e-.34;if(s.add(new et(.075,.075,.04,6),n.dark,[Math.cos(c)*h,.71,-Math.sin(c)*h]),i%2===0){const u=Math.cos(c)*(e-1.1),d=-Math.sin(c)*(e-1.1);s.add(new lt(.46,.22,.66),n.dark,[u,.72,d],[0,c,0],[1,1,1],!0),s.panel([u,.86,d],.3,.54,.07,n.gold,[-Math.PI/2,0,c]),s.cylinder([u,.98,d],.08,.11,.17,t)}}for(let i=0;i<32;i++){const r=i/32*Math.PI*2,o=e-.37;s.add(new lt(.1,.018,i%4===0?.32:.17),i%4===0?t:n.gold,[Math.sin(r)*o,.61,Math.cos(r)*o],[0,r+.35,0])}for(const i of[-1,1])s.tube([[i*2.6,.64,3.6],[i*2.8,.64,2.6],[i*1.8,.64,1.8]],.027,t)}function Ox(s,e,t){const n=s.palette;for(const i of[-1,1]){const r=i*6.25;s.cylinder([r,.22,1.9],.61,.78,.44,n.dark,!0),s.rod([r,.42,1.9],[r,7.6,1.9],.23,n.steel,.2,!0);const o=new De;o.moveTo(i*6.55,6.8),o.bezierCurveTo(i*6.9,10.8,i*3.8,13.9,0,13.8),o.bezierCurveTo(i*3.6,12.45,i*5.5,10.8,i*5.9,7.3),o.closePath();const a=new xt(o,{depth:.76,bevelEnabled:!0,bevelSize:.11,bevelThickness:.1,bevelSegments:2,curveSegments:20,steps:1});s.add(a,n.gold,[0,0,1.5],[0,0,0],[1,1,1],!0);const l=new De;l.moveTo(i*6.24,8.1),l.bezierCurveTo(i*6.18,10.7,i*3.4,13.14,i*1.05,13.43),l.bezierCurveTo(i*3.8,12.35,i*5.54,10.65,i*6.24,8.1),s.add(new xt(l,{depth:.06,bevelEnabled:!1,curveSegments:20}),n.dark,[0,0,1.36],[0,0,0],[1,1,1],!0),s.tube([[r-i*.18,8.05,1.33],[i*5.34,10.72,1.33],[i*3.45,12.37,1.33],[i*1.1,13.43,1.33]],.025,e);for(const c of[1.2,4,7.4])s.ring([r,c,1.9],.28,.055,n.gold);s.panel([r,4.1,1.61],.64,4.9,.16,n.gold),s.panel([r,4.1,1.49],.29,3.7,.08,n.dark)}s.rod([-1.4,12.83,1.9],[1.4,12.83,1.9],.3,n.dark),s.rod([-.5,12.7,1.9],[-.5,9.5,1.9],.027,n.steel),s.rod([.5,12.7,1.9],[.5,9.5,1.9],.027,n.steel),s.rod([-.9,9.5,1.9],[.9,9.5,1.9],.12,n.gold),s.ring([0,9.25,1.9],.26,.075,n.steel,[0,0,0],Math.PI*1.5),Gr(s,t*6.8,-2.9,e,!1),Gr(s,t*6.8,3.8,e,!0)}function Gr(s,e,t,n,i){const r=s.palette,o=Math.sign(e);s.cylinder([e,.32,t],.64,.86,.64,r.dark,!0),s.cylinder([e,.77,t],.44,.55,.34,r.gold,!0),s.ring([e,.78,t],.5,.06,n);const a=[e,1.1,t],l=[e+o*.05,i?5.5:3.8,t+.3],c=[e-o*2.2,i?6.7:4.9,t-.5];s.rod(a,l,.25,r.dark,.21,!0),s.rod(l,c,.18,r.dark,.13);for(const h of[-.27,.27])s.rod([a[0],a[1],a[2]+h],[l[0],l[1],l[2]+h],.085,r.steel),s.piston([e-o*.2,1.5,t+h],[l[0]-o*.26,l[1]-.18,l[2]+h],.085),s.piston([l[0],l[1]-.28,l[2]+h],[c[0]+o*.24,c[1]-.25,c[2]+h],.07);for(let h=0;h<3;h++){const u=vn(a).lerp(vn(l),.25+h*.24);s.panel([u.x,u.y,u.z-.25],.56,.77,.14,h===1?r.dark:r.gold)}for(const h of[a,l,c])s.joint(h,.34,[0,0,1]),s.ring([h[0],h[1],h[2]-.18],.22,.028,n,[0,0,0]);s.tube([[e+o*.28,1,t],[e+o*.4,l[1],t+.3],[c[0],c[1]+.25,c[2]]],.047,r.dark);for(const h of[-1,1])s.rod([c[0],c[1],c[2]+h*.16],[c[0]-o*.52,c[1]-.42,c[2]+h*.24],.06,r.steel),s.rod([c[0]-o*.52,c[1]-.42,c[2]+h*.24],[c[0]-o*.62,c[1]-.6,c[2]+h*.1],.045,r.gold);s.sphere([c[0]-o*.4,c[1]-.3,c[2]],[.08,.08,.08],n)}function Fx(s,e){const t=s.palette,n=e?t.cyan:t.violet;s.cylinder([0,.58,0],.48,.72,1.16,t.dark,!0),s.add(new et(1,1.07,.22,40),t.steel,[0,1.24,0],[0,0,0],[1.65,1,1.25],!0),s.ring([0,1.37,0],1,.025,n),e?(s.sphere([-.5,1.76,0],[.33,.43,.3],t.dark),s.plate([-.5,1.73,0],[.37,.25,.95],t.gold,[Math.PI/2,0,0]),s.sphere([-.5,1.83,-.31],[.21,.045,.04],t.cyan),s.add(new qt(.34),t.crystal,[.65,1.75,0],[0,.3,.2],[.65,1.2,.65])):(s.plate([-.3,1.39,0],[.66,.35,1.8],t.gold,[0,.2,0]),s.rod([.86,1.48,-.65],[.86,1.48,.65],.12,t.steel));for(let i=0;i<4;i++){const r=-1.08+i*.62;s.cylinder([r,1.4,.69],.2,.23,.075,t.dark),s.joint([r,1.58,.68],.15,[0,1,0]),s.rod([r,1.56,.68],[r,1.9+i%2*.14,.68],.072,t.steel),s.ring([r,1.82,.68],.09,.025,n)}for(const i of[-1,1])s.piston([i*1.27,1.46,-.5],[i*1.27,1.46,.35],.048),s.rod([i*.52,.21,0],[i*1.24,1.14,0],.06,t.steel);s.add(new lt(.8,.08,.52),t.dark,[0,1.41,-.86],[.28,0,0],[1,1,1],!0);for(let i=0;i<4;i++)s.add(new lt(.46-i*.065,.012,.025),n,[0,1.465+i*.02,-1.01+i*.072],[.28,0,0])}function zx(s,e){const t=document.createElement("canvas");t.width=1024,t.height=320;const n=t.getContext("2d");n.fillStyle="#061018",n.fillRect(0,0,1024,320),n.strokeStyle="#75684d",n.lineWidth=6,n.strokeRect(8,8,1008,304),n.textAlign="center",n.textBaseline="middle",n.fillStyle="#bcd4dc",n.font='bold 65px "Microsoft YaHei", sans-serif',n.fillText(e.label+" · "+e.kind.toUpperCase(),512,82,950),n.fillStyle="#95abb7",n.font='44px "Microsoft YaHei", sans-serif',n.fillText(e.stage,512,174,950),n.fillStyle="#819096",n.font='36px "Microsoft YaHei", sans-serif',n.fillText("静态装配展示 · 不提供生产功能",512,257,950);const i=new ss(t);i.colorSpace=Ft;const r=new Ge({map:i,toneMapped:!0});r.name="protoss-unit-inscription";const o=new ve(new Gt(3.4,1.06),r);o.name=e.kind+"-name-and-assembly-stage",o.userData.unitLabel=e.label,o.userData.assemblyStage=e.stage,o.userData.decorativeOnly=!0;const a=-e.side*(e.radius-.2);o.position.set(s.x+a-e.side*.08,1.28,s.z-.4),o.rotation.y=-e.side*Math.PI/2,s.root.add(o),s.add(new lt(.12,1.2,3.55),s.palette.gold,[a,1.28,-.4],[0,0,0],[1,1,1],!0),s.add(new lt(.18,.52,.22),s.palette.dark,[a,.78,-.4],[0,0,0],[1,1,1],!0)}function kx(s,e){const t=e.addStaticMesh(s,{tag:"protoss-unit-support",owner:s.name,leafSize:12});s.userData.supportCollisionMeshes=t.length,s.userData.supportCollisionTriangles=t.reduce((n,i)=>n+i.triangleCount,0),s.userData.supportCollisionBoxes=0}function Bx(s,e,t){const n=new qe,i=e.hull,r=e.ceiling,o=e.wallAccent,a=e.wall,l=new Ge({color:6913194});l.name="quiet-violet-assembly";const c=new Ge({color:6658221});c.name="quiet-blue-assembly";const h=new Ke({color:7577010,emissive:2379894,emissiveIntensity:.35,metalness:.38,roughness:.23,flatShading:!0});h.name="cut-psionic-crystal";const u={gold:i,dark:r,ceramic:o,violet:l,cyan:c,crystal:h,steel:a},d=[],f=[-1,1].filter(p=>t.some(m=>m.id===(p<0?"war-forge":"robot-forge")));n.add(Cx(e,f));const g=[{kind:"immortal",label:"不朽者",stage:"装配阶段：护盾矩阵校准",side:-1,z:29,radius:5.7,build:Ix},{kind:"stalker",label:"追猎者",stage:"装配阶段：相位驱动校验",side:-1,z:46,radius:5.3,build:Px},{kind:"dragoon",label:"龙骑士",stage:"装配阶段：粒子炮阵列检修",side:1,z:29,radius:5.7,build:Rx},{kind:"colossus",label:"巨像",stage:"装配阶段：长足底盘联调",side:1,z:46,radius:7.4,build:Lx}].filter(p=>f.includes(p.side));for(const p of g){const{side:m,z:_,radius:v}=p,M=p.kind==="colossus",S=m>0?c:l,E=new rh(n,s,m*21,_,u);Ux(E,v,S);const C=p.build(e);C.name="foundry-"+p.kind,C.position.set(m*21,.66,_),C.userData.unitKind=p.kind,C.userData.label=p.label,C.userData.assemblyStage=p.stage,C.userData.decorativeOnly=!0,C.userData.productionEnabled=!1,n.add(C),kx(C,s),M?(Gr(E,8.2,-2.9,S,!1),Gr(E,8.2,3.8,S,!0)):Ox(E,S,m),zx(E,p),E.finish(p.kind+"-assembly-mount");const z=new ve(new at(v-.95,.023,6,72,Math.PI*1.4),S);z.name=p.kind+"-non-solid-inspection-sweep",z.rotation.x=Math.PI/2,z.position.set(m*21,.77,_),n.add(z),d.push({ring:z,phase:_*.12+m});const T=new Bn(m>0?10207698:11054291,14,15,2);T.name=p.kind+"-assembly-local-fill",T.position.set(m*18,7,_-3),n.add(T);const y=new w1(12766685,M?300:100,M?38:24,.55,.8,2);if(y.name=p.kind+"-assembly-armor-key",y.position.set(m*16.5,M?31:11.5,_-5),y.target.position.set(m*21,M?15:4.2,_),n.add(y,y.target),M){const b=new Bn(7509709,45,18,2);b.name="colossus-upper-carapace-blue-rim",b.position.set(28,24,_+3),n.add(b)}}for(const p of f){const m=new rh(n,s,p*28.5,37.5,u);Fx(m,p>0),m.finish(p>0?"robot-parts-bench":"war-parts-bench")}let x=0;return n.userData.update=p=>{if(!(!Number.isFinite(p)||p<=0)){x+=Math.min(p,.1);for(const m of d)m.ring.rotation.z=x*.19+m.phase}},n.userData.layout={floorY:0,clearCenter:[-4,4],consoleKeepOutRadius:3,exhibitCenters:f.flatMap(p=>[[p*21,29],[p*21,46]]),units:g.map(({kind:p,label:m,stage:_,side:v,z:M,radius:S})=>({kind:p,label:m,stage:_,x:v*21,z:M,radius:S})),decorativeOnly:!0,collision:"Exact tapered plinth meshes; full-height unit triangle BVHs; precise solid rods, physical panels and oval benches. Transparent projections are non-solid."},n}function Vx(s,e,t,n){const i=Bx(e,t,n);return i.name="ship-props",s.add(i),i}function _n(){return{value:null,error:null,updatedAt:0}}const Hx={id:"dashboard",title:"主控台",subtitle:"舰船总览 · MASTER CONSOLE",accent:3725567,create(s){const e=_n(),t=_n(),n=_n(),i=_n(),r=_n();let o=!1;const a=[new dt(()=>s.host.consoleApi.get("/api/overview"),5e3,c=>{e.value=c,e.updatedAt=performance.now(),s.redraw()},c=>{e.error=c,s.redraw()}),new dt(()=>s.host.consoleApi.get("/api/series/latency"),8e3,c=>{t.value=c,s.redraw()}),new dt(()=>s.host.consoleApi.get("/api/series/messages?days=14"),3e4,c=>{n.value=c,s.redraw()}),new dt(()=>s.host.consoleApi.get("/api/stats/usage?hours=24"),3e4,c=>{i.value=c,s.redraw()}),new dt(()=>s.host.consoleApi.get("/api/plugins"),2e4,c=>{typeof c.manage_enabled=="boolean"&&s.shell.setManageEnabled(c.manage_enabled),s.redraw()}),new dt(()=>s.host.consoleApi.get("/api/admin/power"),5e3,c=>{r.value=c,s.redraw()})];async function l(c,h,u){o=!0,s.redraw();const d=await s.host.consoleApi.post(c,h);if(o=!1,d.ok){s.toast(u,"ok");for(const f of a)f.tick()}else s.toast(Hr(d),"error");s.redraw()}return{pollers:a,onFocus(){s.redraw()},draw(c,h){const u=s.shell.status,d=e.value||{},g=!!((r.value||{}).standby??u.standby);c.panel({x:20,y:130,w:330,h:250},{title:"舰体状态 / HULL"});const x=g?.32:Gx(1-(u.plugins.error||0)*.08);c.gauge({x:110,y:300},62,x,{valueText:(x*100).toFixed(0)+"%",label:g?"低功耗":"运转正常",color:g?c.theme.warn:c.theme.ok}),c.keyValue(190,220,150,"运行时长",ni(d.uptime_seconds??u.uptime_seconds)),c.keyValue(190,248,150,"在位插件",String(u.plugins.running)+"/"+String(u.plugins.total)),c.keyValue(190,276,150,"待机时长",g?ni(u.standby_seconds):"—"),c.keyValue(190,304,150,"OneBot",u.online?"已连接":"未连接",u.online?c.theme.ok:c.theme.error),c.keyValue(190,332,150,"版本",String(d.app_version||"—")),c.panel({x:368,y:130,w:636,h:250},{title:"实时指标 / TELEMETRY"});const p=(t.value?.series||[]).map(v=>Number(v.ms||0));c.sparkline({x:388,y:190,w:300,h:84},p.slice(-60),{label:"API 往返延迟",valueText:String(Math.round(t.value?.current_ms??0))+" ms",fill:!0});const m=(n.value?.series||[]).map(v=>Number(v.count||0));c.sparkline({x:706,y:190,w:278,h:84},m.slice(-40),{label:"近 14 天消息量",valueText:vt(d.today_messages)+" / 今日",fill:!0,color:c.theme.ok}),c.keyValue(388,300,280,"今日消息",vt(d.today_messages)),c.keyValue(388,326,280,"累计消息",vt(d.total_messages)),c.keyValue(388,352,280,"模型调用（24h）",vt(i.value?.totals?.calls)),c.keyValue(706,300,278,"24h 消耗",Rs(i.value?.totals?.cost_cny)),c.keyValue(706,326,278,"输入 / 输出",Zi(i.value?.totals?.input_tokens)+" / "+Zi(i.value?.totals?.output_tokens)),c.keyValue(706,352,278,"在线机器人",String(d.bot_nickname||"—")),c.panel({x:20,y:396,w:984,h:158},{title:"舰船指令 / COMMAND",tone:c.theme.warn}),c.text(40,448,g?"舰船当前处于低功耗待机：仅主控台、配置、日志与插件终端在线。":"所有系统在线。危险指令会有二次确认。",{size:17,color:g?c.theme.warn:c.theme.textDim});const _=!o&&g;c.button("power-resume",{x:40,y:468,w:190,h:58},o?"执行中…":"恢复运行",{disabled:!_,tone:c.theme.ok})&&(async()=>await s.confirm({title:"恢复舰船运行",body:"将重建 bot 运行时（回复、记忆、Agent 全部恢复）。期间消息处理会短暂中断。",confirmLabel:"恢复运行"})&&await l("/api/admin/resume",{reason:"星舰主控台恢复"},"已开始恢复运行"))(),c.button("power-standby",{x:246,y:468,w:190,h:58},"进入待机",{disabled:o||g,tone:c.theme.warn})&&(async()=>await s.confirm({title:"进入待机（低功耗）",body:"将停止回复与记忆管线，只保留面板与核心服务。舰内多数终端会随之离线。",confirmLabel:"进入待机",danger:!0})&&await l("/api/admin/standby",{reason:"星舰主控台待机"},"已进入待机"))(),c.button("power-reboot",{x:452,y:468,w:190,h:58},"软重启运行",{disabled:o,tone:c.theme.warn})&&(async()=>await s.confirm({title:"软重启运行",body:"重建运行时并按当前配置重新装配（不重启进程）。",confirmLabel:"软重启",danger:!0})&&await l("/api/admin/reboot",{reason:"星舰主控台软重启"},"已开始软重启"))(),c.button("admin-restart",{x:658,y:468,w:190,h:58},"重启 NeoBot",{disabled:o,tone:c.theme.error})&&(async()=>await s.confirm({title:"重启 NeoBot 进程",body:"整个进程会退出并重新启动，网页面板会短暂断开（本页面随后需要刷新）。",confirmLabel:"确认重启",danger:!0})&&await l("/api/admin/restart",{},"重启指令已下发"))(),c.button("open-console",{x:854,y:562,w:130,h:30},"在面板中打开",{size:15,tone:c.theme.textDim})&&window.open(new URL("../",window.location.href).toString(),"_blank"),h||c.text(40,545,"靠近并按 E 可操作终端",{size:15,color:c.theme.textDim})}}}};function Gx(s){return Math.max(0,Math.min(1,s))}const Wx={id:"bots",title:"通讯台",subtitle:"机器人 · 会话 · COMMS",accent:6480072,create(s){const e=_n(),t=_n(),n=_n(),i=_n();return{pollers:[new dt(()=>s.host.consoleApi.get("/api/bots"),1e4,o=>{e.value=o,s.redraw()},o=>{e.error=o,s.redraw()}),new dt(()=>s.host.consoleApi.get("/api/series/latency"),1e4,o=>{t.value=o,s.redraw()}),new dt(()=>s.host.consoleApi.get("/api/stats/active-users?limit=8"),3e4,o=>{n.value=o,s.redraw()}),new dt(()=>s.host.consoleApi.get("/api/stats/api-calls?limit=8"),15e3,o=>{i.value=o,s.redraw()})],draw(o){const a=(e.value||[])[0]||{},l=!!a.online;o.panel({x:20,y:130,w:470,h:420},{title:"链路状态 / LINK"}),o.text(44,190,l?"● 通讯链路正常":"○ 未检测到 OneBot 连接",{size:24,color:l?o.theme.ok:o.theme.error}),o.keyValue(44,240,420,"昵称",String(a.nickname||a.name||"—")),o.keyValue(44,272,420,"账号",String(a.user_id||"—")),o.keyValue(44,304,420,"平台",String(a.platform||a.app_name||"—")),o.keyValue(44,336,420,"延迟",String(Math.round(Number(t.value?.current_ms??a.latency_ms??0)))+" ms"),o.keyValue(44,368,420,"成功率",String(Math.round(Number(t.value?.success_rate??100)))+"%"),o.keyValue(44,400,420,"今日消息",vt(Number(a.today_messages??0))),o.keyValue(44,432,420,"累计消息",vt(Number(a.total_messages??0))),o.keyValue(44,464,420,"在线时长",ni(Number(a.uptime_seconds??0))),o.sparkline({x:44,y:486,w:420,h:44},(t.value?.series||[]).map(u=>Number(u.ms||0)).slice(-60),{color:o.theme.ok,fill:!0}),o.panel({x:508,y:130,w:496,h:200},{title:"活跃会话 / ACTIVE"});const c=(n.value?.items||[]).slice(0,5);c.length===0&&o.text(532,196,"暂无活跃用户数据",{size:17,color:o.theme.textDim}),c.forEach((u,d)=>{o.keyValue(532,186+d*28,448,String(d+1)+". "+String(u.nickname||u.name||u.user_id||"未知"),vt(Number(u.count??u.value??0)))}),o.panel({x:508,y:348,w:496,h:202},{title:"接口调用排行 / API"});const h=(i.value?.items||[]).slice(0,5);h.length===0&&o.text(532,412,"暂无接口调用记录",{size:17,color:o.theme.textDim}),h.forEach((u,d)=>{o.keyValue(532,404+d*28,448,String(d+1)+". "+String(u.name||u.label||"—"),vt(Number(u.count??u.value??0)))})}}}},Xx={id:"scores",title:"战绩墙",subtitle:"排行榜 · 成就 · RECORDS",accent:13148927,create(s){const e=_n(),t=_n();let n="";const i=[new dt(()=>s.host.gameApi.get("/api/scores?limit=12"+(n?"&game="+encodeURIComponent(n):"")),15e3,r=>{e.value=r,s.redraw()},r=>{e.error=r,s.redraw()}),new dt(()=>s.host.gameApi.get("/api/achievements"),3e4,r=>{t.value=r,s.redraw()})];return{pollers:i,draw(r){r.panel({x:20,y:130,w:560,h:424},{title:"排行榜 / LEADERBOARD"}),[["","全部"],["turret","舱外炮塔"],["repair","损管抢修"]].forEach((c,h)=>{r.button("tab-"+h,{x:40+h*118,y:168,w:110,h:36},c[1],{tone:n===c[0]?r.theme.accent:r.theme.textDim,size:16})&&(n=c[0],i[0].tick())});const a=e.value?.items||[];a.length===0&&r.text(44,260,"还没有成绩记录：去机库玩一局吧。",{size:19,color:r.theme.textDim}),a.slice(0,9).forEach((c,h)=>{const u=228+h*36;r.text(44,u,Yx(h+1),{size:18,color:h<3?r.theme.warn:r.theme.textDim}),r.text(92,u,String(c.player||"舰长"),{size:18}),r.text(300,u,c.game==="repair"?"损管抢修":"舱外炮塔",{size:16,color:r.theme.textDim}),r.text(544,u,vt(c.score),{size:19,align:"right",color:r.theme.accent})}),r.panel({x:600,y:130,w:404,h:424},{title:"成就 / ACHIEVEMENTS"});const l=t.value?.items||[];l.length===0&&(r.text(624,200,"尚未解锁任何成就。",{size:17,color:r.theme.textDim}),r.text(624,230,"试试：首次跃迁、击毁小行星、完成抢修。",{size:15,color:r.theme.textDim})),l.slice(0,10).forEach((c,h)=>{const u=186+h*36;r.text(624,u,"◈ "+String(c.key||""),{size:17,color:r.theme.accent}),r.text(984,u,"×"+String(c.count??1),{size:16,align:"right",color:r.theme.textDim})})}}}};function Yx(s){return String(s).padStart(2,"0")}const qx=[Hx,Wx,Xx],jx={id:"system",title:"太阳核心监控",subtitle:"系统资源 · REACTOR",accent:16757844,decorate(s,e){const t=new ve(new zs(.45,1),new Ge({color:16757844,transparent:!0,opacity:.85}));t.position.set(0,2.4,-.9),s.add(t);const n=new ve(new at(.62,.03,6,32),e.trim);n.position.set(0,2.4,-.9),s.add(n)},create(s){let e=null,t=null,n=null,i=null;const r=[];return{pollers:[new dt(()=>s.host.consoleApi.get("/api/system"),3e3,a=>{e=a,r.push(Number(a.cpu_percent||0)),r.length>120&&r.shift(),s.redraw()},a=>{i=a,s.redraw()}),new dt(()=>s.host.consoleApi.get("/api/tasks"),15e3,a=>{t=a,s.redraw()}),new dt(()=>s.host.consoleApi.get("/api/services"),3e4,a=>{n=a,s.redraw()})],draw(a){const l=e||{};a.panel({x:20,y:130,w:640,h:300},{title:"堆芯负载 / CORE LOAD"});const c=Number(l.cpu_percent||0),h=Number(l.mem_percent||0),u=Number(l.disk_percent||0);a.gauge({x:130,y:280},66,c/100,{valueText:c.toFixed(0)+"%",label:"CPU"+(l.cpu_count?" × "+l.cpu_count:""),color:c>85?a.theme.error:a.theme.accent}),a.gauge({x:340,y:280},66,h/100,{valueText:h.toFixed(0)+"%",label:"内存",color:h>90?a.theme.error:a.theme.ok}),a.gauge({x:550,y:280},66,u/100,{valueText:u.toFixed(0)+"%",label:"存储",color:u>92?a.theme.error:a.theme.warn}),a.keyValue(40,380,300,"进程内存",vt(l.process_memory_mb)+" MB"),a.keyValue(360,380,280,"线程数",vt(l.process_threads)),a.keyValue(40,408,300,"内存明细",vt(l.mem_used_mb)+" / "+vt(l.mem_total_mb)+" MB"),a.keyValue(360,408,280,"磁盘占用",(l.disk_used_gb??0).toFixed(1)+" / "+(l.disk_total_gb??0).toFixed(1)+" GB"),a.panel({x:676,y:130,w:328,h:300},{title:"运行信息 / HOST"}),a.keyValue(696,180,288,"主机",String(l.hostname||"—")),a.keyValue(696,208,288,"系统",String(l.os||"—")),a.keyValue(696,236,288,"Python",String(l.python_version||"—")),a.keyValue(696,264,288,"进程 PID",String(l.pid??"—")),a.keyValue(696,292,288,"NeoBot 运行",ni(s.shell.status.uptime_seconds)),a.keyValue(696,320,288,"负载",(l.load_average||[]).map(x=>x.toFixed(2)).join(" / ")||"—"),a.sparkline({x:696,y:350,w:288,h:60},r.slice(-80),{label:"CPU 曲线",fill:!0}),a.panel({x:20,y:446,w:484,h:108},{title:"后台任务 / TASKS"});const d=t?.scheduled||[],f=t?.background||[];a.keyValue(40,492,444,"定时任务",String(d.length)+" 项"),a.keyValue(40,522,444,"后台作业",String(f.length)+" 项"),t?.scheduled_error&&a.text(40,546,"⚠ "+t.scheduled_error,{size:14,color:a.theme.warn}),a.panel({x:520,y:446,w:484,h:108},{title:"宿主服务 / SERVICES"});const g=(n?.items||[]).slice(0,3);g.length===0&&a.text(540,500,"服务注册表不可用",{size:16,color:a.theme.textDim}),g.forEach((x,p)=>{a.text(540,494+p*24,(x.available===!1?"○ ":"● ")+String(x.name||""),{size:16,color:x.available===!1?a.theme.warn:a.theme.ok})}),i&&a.text(24,128,"",{size:12})}}}},Kx={id:"usage",title:"能量分配",subtitle:"模型用量 · POWER GRID",accent:8184063,create(s){const e=oh(),t=oh();return{pollers:[new dt(()=>s.host.consoleApi.get("/api/stats/usage?hours=24"),2e4,i=>{e.value=i,s.redraw()},i=>{e.error=i,s.redraw()}),new dt(()=>s.host.consoleApi.get("/api/series/usage?hours=24&bucket=hour"),3e4,i=>{t.value=i,s.redraw()})],draw(i){const r=e.value?.totals||{},o=t.value?.points||[];i.panel({x:20,y:130,w:984,h:190},{title:"总功率 / TOTALS"}),i.gauge({x:130,y:230},58,Math.min(1,Number(r.calls||0)/200),{valueText:vt(r.calls),label:"调用次数"}),i.gauge({x:330,y:230},58,Math.min(1,Number(r.input_tokens||0)/5e5),{valueText:Zi(r.input_tokens),label:"输入 Token",color:i.theme.ok}),i.gauge({x:530,y:230},58,Math.min(1,Number(r.output_tokens||0)/2e5),{valueText:Zi(r.output_tokens),label:"输出 Token",color:i.theme.warn}),i.gauge({x:730,y:230},58,Math.min(1,Number(r.cost_cny||0)/20),{valueText:Rs(r.cost_cny),label:"24h 花费",color:"#ff9ad5"}),i.sparkline({x:830,y:170,w:154,h:120},o.map(c=>Number(c.cost_cny||0)),{label:"开销曲线",fill:!0,color:"#ff9ad5"}),i.panel({x:20,y:336,w:484,h:218},{title:"按模块 / MODULES"});const a=(e.value?.items||[]).slice(0,7);a.length===0&&i.text(44,400,e.value?.available===!1?"用量库不可用":"24 小时内没有模型调用",{size:17,color:i.theme.textDim}),a.forEach((c,h)=>{const u=386+h*22;i.text(44,u,String(c.module||"未知模块").slice(0,18),{size:16}),i.text(300,u,vt(c.calls)+" 次",{size:15,color:i.theme.textDim}),i.text(484,u,Rs(c.cost_cny),{size:16,align:"right",color:i.theme.accent})}),i.panel({x:520,y:336,w:484,h:218},{title:"按模型 / MODELS"});const l=(t.value?.models||[]).slice(0,7);l.length===0&&i.text(544,400,"暂无模型用量明细",{size:17,color:i.theme.textDim}),l.forEach((c,h)=>{const u=386+h*22,d=String(c.model_name||c.name||c.model||"未知模型");i.text(544,u,d.slice(0,22),{size:16}),i.text(784,u,Zi(Number(c.total_tokens||0)),{size:15,color:i.theme.textDim}),i.text(984,u,Rs(Number(c.cost_cny||0)),{size:16,align:"right",color:i.theme.accent})})}}}},Zx={id:"plugins",title:"模块机架",subtitle:"插件装载 · MODULE RACK",accent:9109448,decorate(s,e){for(let t=0;t<4;t+=1){const n=new ve(new lt(.28,.5,.36),e.prop);n.position.set(-1.1+t*.72,2.3,-.75),s.add(n);const i=new ve(new lt(.16,.04,.02),e.emissive);i.position.set(-1.1+t*.72,2.5,-.56),s.add(i)}},create(s){let e=null,t=null,n="",i=!1;const r=[new dt(()=>s.host.consoleApi.get("/api/plugins"),12e3,a=>{e=a,typeof a.manage_enabled=="boolean"&&s.shell.setManageEnabled(a.manage_enabled),!n&&(a.items||[]).length>0&&(n=String((a.items||[])[0].id||"")),s.redraw()},a=>{t=a,s.redraw()})];async function o(a,l){const c=(e?.items||[]).find(f=>f.id===a),h=c?!c.enabled:!0;if(!await s.confirm({title:l==="toggle"?h?"启用模块 "+a:"停用模块 "+a:"重载模块 "+a,body:l==="toggle"?h?"模块会立即装载并启动。":"模块会立即停止；依赖它的模块会被联动停用（前置插件满足后会自动恢复）。":"模块会重新导入并重启，期间它的功能短暂不可用。",confirmLabel:l==="toggle"?h?"启用":"停用":"重载",danger:l==="toggle"&&!h}))return;i=!0,s.redraw();const d=await s.host.consoleApi.post("/api/plugins/"+encodeURIComponent(a)+"/"+l,{});i=!1,d.ok?s.toast(d.data?.message||"操作完成","ok"):s.toast(Hr(d),"error"),r[0].tick(),s.redraw()}return{pollers:r,draw(a){const l=e?.items||[];a.panel({x:20,y:130,w:520,h:424},{title:"模块清单 / MODULES ("+l.length+")"});const c=l.map(d=>({label:d.name+(d.official?" · 官方":""),sub:"v"+String(d.version||"?")+(d.auto_disabled?" · 依赖未满足":"")+(d.dependency_issues&&d.dependency_issues.length>0?" · "+d.dependency_issues[0]:""),badge:d.status==="running"?"运行中":d.enabled===!1?"已停用":d.status||"",tone:d.status==="running"?a.theme.ok:d.auto_disabled?a.theme.warn:d.status==="error"?a.theme.error:a.theme.textDim,active:d.id===n})),h=a.list("plugins",{x:36,y:168,w:488,h:372},c,{rowHeight:46});h>=0&&l[h]&&(n=String(l[h].id||""));const u=l.find(d=>d.id===n)||l[0];if(a.panel({x:556,y:130,w:448,h:424},{title:"模块详情 / DETAIL"}),!u)a.text(580,200,"没有可显示的模块",{size:18,color:a.theme.textDim});else{a.text(580,186,u.name,{size:26,weight:"bold"}),a.text(580,214,u.description||"（无描述）",{size:15,color:a.theme.textDim,maxWidth:400}),a.keyValue(580,252,400,"版本",String(u.version||"—")),a.keyValue(580,276,400,"状态",String(u.status||"—")),a.keyValue(580,300,400,"作者",String(u.author||"—")),a.keyValue(580,324,400,"热重载",u.hot_reload===!1?"不支持":"支持"),u.dependencies&&u.dependencies.length>0&&a.keyValue(580,348,400,"前置插件",u.dependencies.join(", ")),u.dependents&&u.dependents.length>0&&a.keyValue(580,372,400,"被依赖",u.dependents.join(", ")),u.disabled_reason&&a.text(580,402,"⚠ "+u.disabled_reason,{size:14,color:a.theme.warn,maxWidth:400}),u.dependency_issues&&u.dependency_issues.length>0&&a.text(580,424,"未满足："+u.dependency_issues.join("；"),{size:14,color:a.theme.warn,maxWidth:400});const d=s.shell.availability("plugins").readOnly||i;a.button("toggle",{x:580,y:452,w:190,h:52},u.enabled===!1?"装载模块":"停用模块",{disabled:d,tone:u.enabled===!1?a.theme.ok:a.theme.warn})&&o(String(u.id),"toggle"),a.button("reload",{x:786,y:452,w:198,h:52},i?"执行中…":"热重载",{disabled:d||u.official===!0,tone:a.theme.accent})&&o(String(u.id),"reload"),a.text(580,528,"依赖未满足的模块会被自动停用，前置插件恢复后自动装载。",{size:14,color:a.theme.textDim,maxWidth:400})}t&&a.text(24,120,"⚠ "+t,{size:15,color:a.theme.error})}}}};function oh(){return{value:null,error:null,updatedAt:0}}const Jx=[jx,Kx,Zx],$x={id:"logs",title:"航行日志",subtitle:"实时日志 · SHIP LOG",accent:10474751,create(s){let e=[],t=null,n="ALL";const i=["ALL","INFO","WARNING","ERROR","DEBUG"];let r=!0;return{pollers:[new dt(()=>s.host.consoleApi.get("/api/logs?limit=120"),4e3,a=>{e=a.items||[],s.redraw()},a=>{t=a,s.redraw()})],draw(a){a.panel({x:20,y:130,w:984,h:424},{title:"日志流 / STREAM"}),i.forEach((u,d)=>{a.button("lv-"+u,{x:40+d*96,y:164,w:88,h:32},u,{tone:n===u?a.theme.accent:a.theme.textDim,size:15})&&(n=u,a.scrollReset("logs"))}),a.button("follow",{x:856,y:164,w:128,h:32},r?"自动滚动：开":"自动滚动：关",{tone:r?a.theme.ok:a.theme.textDim,size:15})&&(r=!r);const l=e.filter(u=>n==="ALL"?!0:String(u.level||"").toUpperCase().startsWith(n.slice(0,4))),c=l.slice().reverse().map(u=>({label:"["+mx(u.time||u.datetime)+"] "+String(u.message||"").slice(0,68),sub:String(u.module||"")+" · "+String(u.level||"").toLowerCase(),tone:String(u.level||"").toUpperCase().startsWith("ERR")?a.theme.error:String(u.level||"").toUpperCase().startsWith("WARN")?a.theme.warn:void 0})),h=a.list("logs",{x:36,y:206,w:952,h:330},c,{rowHeight:40});if(h>=0){const u=l.slice().reverse()[h];u&&s.toast(String(u.module||"")+": "+String(u.message||""),"info")}a.text(24,574,"共 "+String(l.length)+" 条 · 点击条目可在舰桥广播完整内容",{size:14,color:a.theme.textDim}),t&&a.text(700,574,"⚠ "+t,{size:14,color:a.theme.error})}}}},Qx={id:"analysis",title:"神经矩阵",subtitle:"提示词分析 · NEURAL MATRIX",accent:16747224,decorate(s){for(let e=0;e<3;e+=1){const t=new ve(new at(.5+e*.18,.02,6,40),new Ge({color:16747224,transparent:!0,opacity:.5-e*.1}));t.position.set(0,2.5,-.9),t.rotation.x=Math.PI/2+e*.4,s.add(t)}},create(s){let e=null,t=null,n=0;return{pollers:[new dt(()=>s.host.consoleApi.get("/api/analysis/prompts"),3e4,r=>{e=r,s.redraw()},r=>{t=r,s.redraw()})],draw(r){const o=e2(e);r.panel({x:20,y:130,w:430,h:424},{title:"分析对象 / SOURCES ("+o.length+")"});const a=o.map(h=>({label:String(h.name||h.label||h.key||h.agent||"未命名"),sub:"约 "+String(Math.round(Number(h.tokens??h.estimated_tokens??0)))+" tokens · "+String(h.chars??0)+" 字符",active:o[n]===h})),l=r.list("analysis",{x:36,y:168,w:398,h:370},a,{rowHeight:44});l>=0&&(n=l),r.panel({x:466,y:130,w:538,h:424},{title:"矩阵详情 / DETAIL"});const c=o[n];if(!c)r.text(490,200,t?"⚠ "+t:"等待分析数据…",{size:18,color:t?r.theme.error:r.theme.textDim});else{r.text(490,190,String(c.name||c.label||c.key||"未命名"),{size:26,weight:"bold"});const h=Number(c.tokens??c.estimated_tokens??0);r.gauge({x:590,y:300},62,Math.min(1,h/8e3),{valueText:Math.round(h)+"",label:"估算 tokens"}),r.keyValue(700,250,284,"字符数",String(c.chars??0)),r.keyValue(700,278,284,"估算 tokens",String(Math.round(h))),r.keyValue(700,306,284,"来源",String(c.agent||c.key||"—"));const u=(c.sections||[]).slice(0,6);u.length===0&&r.text(490,400,"没有分段信息（该来源不提供分段统计）",{size:15,color:r.theme.textDim}),u.forEach((d,f)=>{const g=396+f*24;r.text(490,g,String(d.name||"段落"),{size:15,color:r.theme.textDim}),r.text(960,g,String(Math.round(Number(d.tokens??0)))+" tok",{size:15,align:"right"})}),r.text(490,540,"提示词分析不调用模型，仅统计装配后的字符与估算 token。",{size:14,color:r.theme.textDim,maxWidth:480})}}}}};function e2(s){if(!s)return[];if(Array.isArray(s.items))return s.items;if(Array.isArray(s.sources))return s.sources;const e=[];for(const[t,n]of Object.entries(s))if(n&&typeof n=="object"&&!Array.isArray(n)){const i=n;(typeof i.chars=="number"||typeof i.tokens=="number"||Array.isArray(i.sections))&&e.push({key:t,name:String(i.name||t),...i})}return e}const t2={id:"config",title:"舰载系统配置",subtitle:"本体配置 · SHIP CONFIG",accent:9419007,create(s){let e=null,t=null,n=null,i="",r=!1,o=null;const a=[new dt(()=>s.host.consoleApi.get("/api/config"),2e4,u=>{e=u,s.redraw()},u=>{n=u,s.redraw()}),new dt(()=>s.host.consoleApi.get("/api/config/env"),3e4,u=>{t=u,s.redraw()})],l=()=>(e?.schema||[]).filter(u=>u.kind==="group");async function c(u,d){if(!e)return;const f=JSON.parse(JSON.stringify(e.config||{}));let g=f;for(let p=0;p<u.length-1;p+=1){const m=u[p],_=g[m];(!_||typeof _!="object")&&(g[m]={}),g=g[m]}g[u[u.length-1]]=d,r=!0,s.redraw();const x=await s.host.consoleApi.post("/api/config",{revision:e.revision,config:f});r=!1,x.ok?(e=x.data||e,s.toast(x.data?.message||"配置已写入 config.toml","ok"),a[0].tick()):s.toast(Hr(x),"error"),s.redraw()}function h(u,d){if(d==="bool"||d==="boolean")return u==="true"||u==="是"||u==="1";if(d==="int"||d==="integer")return Number.parseInt(u,10);if(d==="float"||d==="number")return Number.parseFloat(u);const f=u.trim();if(f.startsWith("[")||f.startsWith("{"))try{return JSON.parse(f)}catch{return u}return u}return{pollers:a,draw(u){const d=l();u.panel({x:20,y:130,w:320,h:424},{title:"分区 / SECTIONS ("+d.length+")"});const f=d.map(m=>({label:String(m.name||(m.path||[]).join(".")),sub:String(m.description||"").slice(0,22)||"config.toml",active:i===String(m.name)})),g=u.list("config-sections",{x:36,y:168,w:288,h:370},f,{rowHeight:46});g>=0&&d[g]&&(i=String(d[g].name||""));const x=s.shell.availability("config").readOnly;u.panel({x:356,y:130,w:648,h:424},{title:"参数 / PARAMETERS"});const p=d.find(m=>String(m.name)===i)||d[0];if(!p)u.text(380,200,n?"⚠ "+n:"正在读取 config.toml…",{size:18,color:n?u.theme.error:u.theme.textDim});else{i=String(p.name||"");const m=(p.fields||[]).filter(_=>!_.hidden).slice(0,9);if(u.text(380,176,String(p.name||"")+"  ·  "+String(p.description||""),{size:17,color:u.theme.textDim,maxWidth:600}),m.forEach((_,v)=>{const M=216+v*40;u.isHovered("field-"+v);const S=String(_.name||""),E=_.value,C=E==null?"（未设置）":typeof E=="object"?JSON.stringify(E).slice(0,26):String(E),z={x:380,y:M-20,w:600,h:34};if(u.textField("field-"+v,z,S+"  =  "+C,{placeholder:S,focused:o!==null&&o.path===(_.path||[]).join(".")}).clicked&&!x&&_.kind==="scalar"){const y=_.path||[String(_.name)];o={path:y.join("."),value:E==null?"":String(E)},s.host.textCapture.open({initial:o.value,onType:b=>{o&&(o.value=b),s.redraw()},onCommit:b=>{o=null,c(y,h(b,String(_.type||"")))},onCancel:()=>{o=null,s.redraw()}})}}),u.button("config-reload",{x:380,y:496,w:170,h:44},r?"执行中…":"重载配置",{disabled:r,tone:u.theme.accent,size:16})&&(async()=>{if(!await s.confirm({title:"重载运行配置",body:"按磁盘上的 config.toml 重新装配运行期组件（等价于面板的「重载运行配置」）。",confirmLabel:"重载"}))return;r=!0,s.redraw();const v=await s.host.consoleApi.post("/api/config/reload",{});r=!1,s.toast(v.ok?v.data?.message||"配置已重载":Hr(v),v.ok?"ok":"error"),a[0].tick(),s.redraw()})(),u.button("env-open",{x:560,y:496,w:200,h:44},"环境变量密钥",{size:16})){const _=n2(t);s.toast(_.length>0?"已配置 "+_.length+" 个密钥："+_.slice(0,6).join("、")+"（Key 只写不读，需在面板编辑）":"尚未配置任何 API 密钥","info")}x?u.text(380,476,"当前为只读模式：无法保存配置",{size:15,color:u.theme.warn}):u.text(380,552,"点击任意参数行即可修改；保存会写入 config.toml 并做一次校验。",{size:14,color:u.theme.textDim,maxWidth:600})}}}}};function n2(s){if(!s)return[];const t=(s.items||s.entries||[]).map(n=>String(n.key||"")).filter(n=>n.length>0);return t.length>0?t:Array.isArray(s.keys)?s.keys.map(n=>String(n)):[]}const i2=[$x,Qx,t2],Vi=["天鹅座 λ-4","猎户悬臂 K-17","南门二 β","天苑四 ε","蛇夫座 9","武仙座 τ","船底座 HD-7","仙女座 M31-附","半人马 ζ","天琴座 Vega-2"],s2={id:"navigation",title:"星图导航台",subtitle:"星图 · 跃迁 · NAVIGATION",accent:7327999,decorate(s,e){const t=new ve(new ft(.34,20,14),new Ge({color:7327999,wireframe:!0,transparent:!0,opacity:.75}));t.position.set(0,2.5,-.7),s.add(t);const n=new ve(new at(.5,.012,6,40),e.trim);n.position.set(0,2.5,-.7),n.rotation.x=Math.PI/2.4,s.add(n)},create(s){let e=0,t="";return{idleAnimated:!0,draw(n){const i=s.host.actions,r=i.warping();n.panel({x:20,y:130,w:620,h:424},{title:"星图 / STARCHART"});const o=i.systemName(),a=Vi[(e+1)%Vi.length];n.text(44,200,"当前星系",{size:16,color:n.theme.textDim}),n.text(44,236,o,{size:30,weight:"bold"}),n.text(44,292,"目标星系",{size:16,color:n.theme.textDim}),n.text(44,328,a,{size:30,weight:"bold",color:n.theme.accent});const l=(4.2+e*1.7).toFixed(1);n.keyValue(44,372,560,"航程",l+" 光年"),n.keyValue(44,400,560,"预计跃迁耗时","约 3 秒"),n.keyValue(44,428,560,"引擎状态",r?"跃迁中…":"就绪"),n.button("nav-prev",{x:44,y:456,w:120,h:48},"上一个",{size:17})&&(e=(e+Vi.length-1)%Vi.length),n.button("nav-next",{x:176,y:456,w:120,h:48},"下一个",{size:17})&&(e=(e+1)%Vi.length),n.button("nav-jump",{x:308,y:456,w:220,h:48},r?"跃迁进行中":"启动跃迁",{disabled:r,tone:n.theme.accent})&&i.triggerWarp(!0,(e+1)%Vi.length)&&(t="跃迁引擎已点火："+a,n.scrollReset("nav")),n.text(44,532,t||"跃迁会让全舰进入高速航行状态，舷窗外会变成星流。",{size:15,color:n.theme.textDim,maxWidth:560}),n.panel({x:656,y:130,w:348,h:424},{title:"航道提示 / NOTES"}),n.text(680,200,"· 随机跃迁",{size:17,color:n.theme.accent}),n.text(680,228,"航行一段时间后，舰载 AI 会",{size:15,color:n.theme.textDim}),n.text(680,250,"自动规划一次跃迁。",{size:15,color:n.theme.textDim}),n.text(680,296,"· 手动跃迁",{size:17,color:n.theme.accent}),n.text(680,324,"在本终端选择目标星系并点火。",{size:15,color:n.theme.textDim}),n.text(680,370,"· 星穹舰桥",{size:17,color:n.theme.accent}),n.text(680,398,"跃迁后星云配色与行星都会改变，",{size:15,color:n.theme.textDim}),n.text(680,420,"透过舰桥护盾观察新的星系。",{size:15,color:n.theme.textDim});const c=s.host.jumpIntervalMinutes;n.text(680,480,c>0?"自动跃迁间隔：约 "+c+" 分钟":"自动跃迁已关闭",{size:15,color:n.theme.textDim})}}}},r2=[{id:"espresso",name:"双份浓缩",desc:"短时间提升移动速度",boost:"sprint",seconds:45},{id:"cocoa",name:"舰载可可",desc:"暖胃，纯粹好喝",boost:null,seconds:0},{id:"tea",name:"合成红茶",desc:"提升跳跃高度一点点",boost:"jump",seconds:40}],o2={id:"coffee",title:"咖啡机",subtitle:"船员补给 · GALLEY",accent:16764810,create(s){let e=0,t=0;return{draw(n){n.panel({x:20,y:130,w:640,h:424},{title:"菜单 / MENU"}),r2.forEach((o,a)=>{const l=190+a*78,c={x:44,y:l,w:592,h:64},h=n.isHovered("drink-"+a);n.panel(c,{tone:e===a||h?n.theme.accent:n.theme.panelEdge}),n.text(64,l+28,o.name,{size:22,color:n.theme.text}),n.text(64,l+52,o.desc,{size:15,color:n.theme.textDim}),n.button("pour-"+a,{x:500,y:l+12,w:118,h:40},"接一杯",{size:16})&&(e=a,t+=1,s.host.actions.playChime("coffee"),s.toast("接了一杯"+o.name+"，舰桥的空气里都是香味。","ok"),o.boost&&(s.host.actions.boost(o.boost,o.seconds),s.toast("获得增益："+o.desc+"（"+o.seconds+" 秒）","info")),s.host.actions.unlockAchievement("galley-visit","在休息厅接了一杯饮品"))}),n.panel({x:684,y:130,w:320,h:424},{title:"状态 / STATUS"}),n.text(708,200,"今日供应",{size:16,color:n.theme.textDim}),n.text(708,236,String(t)+" 杯",{size:32,weight:"bold",color:n.theme.accent}),n.text(708,300,"增益",{size:16,color:n.theme.textDim});const i=s.host.actions.boostRemaining("sprint"),r=s.host.actions.boostRemaining("jump");n.text(708,336,i>0?"疾跑 +25%（"+i.toFixed(0)+"s）":"无",{size:18}),n.text(708,368,r>0?"跳跃 +15%（"+r.toFixed(0)+"s）":"无",{size:18}),n.text(708,440,"提示：按住 Ctrl 疾跑。",{size:15,color:n.theme.textDim})}}}},ah=[{id:"bridge",name:"舰桥主题",scale:[220,277,330,415,494]},{id:"warp",name:"跃迁回响",scale:[196,233,294,349,392]},{id:"hangar",name:"机库节拍",scale:[262,311,392,466,523]}],a2={id:"jukebox",title:"点唱机",subtitle:"船员娱乐 · JUKEBOX",accent:13214463,create(s){let e=-1,t=0;const n=new Array(18).fill(0);return{idleAnimated:!0,draw(i){const r=e>=0;i.panel({x:20,y:130,w:984,h:424},{title:"曲库 / LIBRARY"}),ah.forEach((o,a)=>{const l=178+a*56;i.text(48,l+24,(e===a?"▶ ":"· ")+o.name,{size:20,color:e===a?i.theme.accent:i.theme.text}),i.button("track-"+a,{x:760,y:l+4,w:110,h:40},e===a?"停止":"播放",{size:16})&&(e===a?(e=-1,s.host.actions.stopMusic()):(e=a,s.host.actions.playMusic(o.scale)))}),t+=1;for(let o=0;o<n.length;o+=1){const a=r?Math.abs(Math.sin(t*.05+o*.7))*(.4+Math.random()*.6):.04;n[o]=n[o]*.7+a*.3}i.panel({x:48,y:360,w:928,h:170},{title:"频谱 / SPECTRUM"}),n.forEach((o,a)=>{const l=Math.max(4,o*120);i.ctx.fillStyle=a%2===0?i.theme.accent:i.theme.ok,i.ctx.fillRect(72+a*50,506-l,30,l)}),i.text(48,546,r?"正在播放："+ah[e].name+"（合成音律，无外部音频文件）":"点「播放」试试，音效由 WebAudio 实时合成。",{size:15,color:i.theme.textDim}),s.host.actions.setMusicActive(r)}}}},l2={id:"vitals",title:"生命体征仪",subtitle:"舰体诊断 · MEDBAY",accent:9109456,create(s){let e=null;const t=[];return{pollers:[new dt(()=>s.host.consoleApi.get("/api/system"),3e3,i=>{e=i,t.push(Number(i.cpu_percent||0)),t.length>120&&t.shift(),s.redraw()})],draw(i){const r=e||{};i.panel({x:20,y:130,w:984,h:424},{title:"舰体体征 / VITALS"});const o=.5+.5*Math.sin(performance.now()/380);i.gauge({x:180,y:300},88,Number(r.cpu_percent||0)/100,{valueText:String(Math.round(Number(r.cpu_percent||0)))+"%",label:"神经活动（CPU）",color:i.theme.ok}),i.gauge({x:440,y:300},88,Number(r.mem_percent||0)/100,{valueText:String(Math.round(Number(r.mem_percent||0)))+"%",label:"体液循环（内存）"}),i.gauge({x:700,y:300},88,o,{valueText:"正常",label:"心跳（进程）",color:i.theme.accent}),i.sparkline({x:836,y:240,w:148,h:120},t.slice(-80),{label:"心电图",fill:!0,color:i.theme.ok}),i.keyValue(48,420,400,"舰体运行时长",ni(s.shell.status.uptime_seconds)),i.keyValue(48,450,400,"进程内存",vt(r.process_memory_mb)+" MB"),i.keyValue(48,480,400,"线程数",vt(r.process_threads)),i.keyValue(520,420,460,"磁盘占用",(r.disk_used_gb??0).toFixed(1)+" / "+(r.disk_total_gb??0).toFixed(1)+" GB"),i.keyValue(520,450,460,"主机",String(r.hostname||"—")),i.keyValue(520,480,460,"系统",String(r.os||"—")),i.text(48,528,"医务室建议：CPU 长期高于 85% 时，考虑减少并发任务。",{size:15,color:i.theme.textDim})}}}},c2={id:"supplies",title:"补给箱",subtitle:"随身物资 · SUPPLIES",accent:16765567,create(s){let e=0;return{draw(t){t.panel({x:20,y:130,w:984,h:424},{title:"物资清单 / INVENTORY"}),t.text(48,200,"已开启补给："+e+" 箱",{size:24}),[["应急口粮",e>0?"×1":"未领取"],["磁力靴保养包",e>1?"×1":"未领取"],["备用氧烛",e>2?"×1":"未领取"]].forEach((i,r)=>{t.keyValue(48,256+r*40,460,i[0],i[1])}),t.button("open-supply",{x:48,y:420,w:220,h:56},"开启补给箱",{tone:t.theme.warn})&&(e+=1,s.host.actions.playChime("supply"),s.toast("补给箱已开启（第 "+e+" 箱）。","ok"),s.host.actions.unlockAchievement("supply-run","开启货舱补给箱"),s.redraw()),t.text(48,512,"补给只是仪式感：真正让这艘船运转的是后排那台服务器。",{size:15,color:t.theme.textDim})}}}},h2={id:"telescope",title:"天文望远镜",subtitle:"舰外观测 · TELESCOPE",accent:11067647,create(s){const e=["主行星","伴星卫星","小行星带","航道上的货船"];let t=0,n=1;return{draw(i){i.panel({x:20,y:130,w:640,h:424},{title:"观测目标 / TARGETS"}),e.forEach((r,o)=>{i.button("target-"+o,{x:44,y:180+o*60,w:360,h:48},r,{tone:t===o?i.theme.accent:i.theme.textDim})&&(t=o,s.host.actions.lookAtTarget(r),s.host.actions.unlockAchievement("stargazer","用望远镜观测舰外天体"))}),i.text(44,452,"倍率",{size:16,color:i.theme.textDim}),i.progress({x:44,y:466,w:360,h:16},n,{label:"",color:i.theme.accent}),i.button("zoom-in",{x:424,y:452,w:90,h:40},"放大",{size:16})&&(n=Math.min(1,n+.2),s.host.actions.zoomView(1.2)),i.button("zoom-out",{x:524,y:452,w:90,h:40},"缩小",{size:16})&&(n=Math.max(.1,n-.2),s.host.actions.zoomView(1/1.2)),i.panel({x:684,y:130,w:320,h:424},{title:"观测记录 / LOG"}),i.text(708,200,"当前目标是「"+e[t]+"」。",{size:17,maxWidth:280}),i.text(708,244,"放大/缩小会改变视野（FOV），",{size:15,color:i.theme.textDim,maxWidth:280}),i.text(708,266,"把光标对准舷窗外即可观察。",{size:15,color:i.theme.textDim,maxWidth:280}),i.text(708,330,"提示：观景廊的舷窗视野最好。",{size:15,color:i.theme.textDim,maxWidth:280})}}}},u2={id:"captain-chair",title:"舰长席",subtitle:"指挥席 · CAPTAIN",accent:16765088,create(s){return{draw(e){const t=s.host.actions.isSeated();e.panel({x:20,y:130,w:984,h:424},{title:"舰长日志 / CAPTAIN LOG"}),e.text(48,210,t?"已就座：视野降低，移动暂停。":"尚未就座。",{size:24}),e.button("seat",{x:48,y:260,w:220,h:56},t?"起身":"坐下",{tone:e.theme.accent})&&(s.host.actions.setSeated(!t),s.redraw());const n=s.shell.status;e.keyValue(48,360,900,"舰船状态",n.standby?"低功耗待机":"全系统运行"),e.keyValue(48,392,900,"在位插件",String(n.plugins.running)+" / "+String(n.plugins.total)),e.keyValue(48,424,900,"通讯链路",n.online?"正常":"中断"),e.keyValue(48,456,900,"运行时长",ni(n.uptime_seconds)),e.text(48,512,"舰长须知：所有面板都在舰上；待机时部分终端会进入低功耗。",{size:15,color:e.theme.textDim})}}}},d2=[s2,o2,a2,l2,c2,h2,u2];function cu(s){return{id:s.id,title:s.title,subtitle:s.subtitle,accent:s.accent,kind:"minigame",create(e){let t=null,n=0;return{pollers:[new dt(()=>e.host.gameApi.get("/api/scores?game="+encodeURIComponent(s.id)+"&limit=5"),2e4,r=>{t=r,n=Math.max(n,Number((r.items||[])[0]?.score??0)),e.redraw()})],idleAnimated:!0,draw(r){r.panel({x:20,y:130,w:600,h:424},{title:"演练说明 / BRIEFING"}),r.text(44,190,s.description,{size:20,maxWidth:552}),s.howTo.forEach((a,l)=>{r.text(44,236+l*30,"· "+a,{size:17,color:r.theme.textDim,maxWidth:552})}),r.button("start",{x:44,y:470,w:240,h:60},"开始演练",{tone:r.theme.accent,disabled:!!e.shell.status.standby})&&e.host.actions.openMinigame(s.id,e.anchor.spec.id),r.text(300,508,"按 E 离开终端 · 演练中按 E / Esc 可随时退出",{size:15,color:r.theme.textDim}),r.panel({x:640,y:130,w:364,h:424},{title:"最佳成绩 / BEST"});const o=t?.items||[];o.length===0&&r.text(664,200,"还没有记录，去创造第一份成绩。",{size:17,color:r.theme.textDim,maxWidth:320}),o.forEach((a,l)=>{const c=196+l*40;r.text(664,c,String(l+1)+". "+String(a.player||"舰长"),{size:18}),r.text(984,c,vt(a.score),{size:18,align:"right",color:r.theme.accent})}),r.text(664,470,s.scoreLabel,{size:15,color:r.theme.textDim}),r.text(664,500,"当前最佳："+vt(n),{size:18})}}}}}const f2=cu({id:"turret",title:"炮塔模拟器",subtitle:"舱外炮塔 · TURRET",accent:16747114,description:"小行星群正在接近。坐上舷侧炮塔，把它们打成碎片。",howTo:["移动鼠标瞄准，左键开火（每 0.18 秒一发）","小行星撞上舰体会扣完整度，归零即演练失败","每 14 秒来一波，波次越高速度越快","完整度越高，结算奖励分越多"],scoreLabel:"击毁得分（含完整度奖励）"}),p2=cu({id:"repair",title:"损管终端",subtitle:"损管抢修 · DAMAGE CONTROL",accent:16762977,description:"太阳核心回路被震断，限时把电力从堆芯接到各个系统。",howTo:["点击导线格子让它旋转 90°","绿色表示已通电，橙色边框是必须接通的系统","接通全部系统即过关，剩余时间折算分数","共三轮，每轮时间更短、网格更乱"],scoreLabel:"抢修得分（含剩余时间奖励）"}),m2=[f2,p2],hu=[...qx,...Jx,...i2,...d2,...m2];Object.fromEntries(hu.map(s=>[s.id,s]));function g2(){return hu}class v2{modules=new Map;register(e){this.modules.set(e.id,e)}get(e){return this.modules.get(e)}list(){return[...this.modules.values()]}}const uu=new v2;function du(s){uu.register(s)}const x2=14,br=200,_2=9,Hi={minX:-78,maxX:78,minY:-4,maxY:15,minZ:-24,maxZ:24};class y2{id="turret";name="舱外炮塔";description="小行星群正在接近，用舷侧炮塔把它们打成碎片。";icon="target";mode="world";ctx=null;group=null;asteroids=[];bolts=[];bursts=[];yaw=0;pitch=0;elapsed=0;waveTimer=0;wave=1;score=0;hull=br;destroyed=0;fireCooldown=0;ended=!1;viewpoint(){return{position:new w(46,12.4,26),yaw:Math.PI,pitch:-.05}}start(e){this.ctx=e,this.group=new qe,this.group.name="minigame-turret",e.scene.add(this.group),this.asteroids=[],this.bolts=[],this.bursts=[],this.elapsed=0,this.waveTimer=0,this.wave=1,this.score=0,this.hull=br,this.destroyed=0,this.ended=!1,this.yaw=Math.PI,this.pitch=-.05,this.spawnWave(4),e.setHud({title:"舱外炮塔",score:"得分 0",extra:"舰体完整度 100%",hint:"移动鼠标瞄准 · 左键开火 · Esc/E 退出"})}spawnWave(e){const t=this.ctx;if(!(!t||!this.group))for(let n=0;n<e;n+=1){const i=4+t.rng()*10,r=new zs(i,1),o=r.attributes.position;for(let f=0;f<o.count;f+=1){const g=.75+t.rng()*.5;o.setXYZ(f,o.getX(f)*g,o.getY(f)*g,o.getZ(f)*g)}r.computeVertexNormals();const a=new ve(r,new Ke({color:9209208,roughness:.95,flatShading:!0})),l=(t.rng()-.5)*1.2+Math.PI,c=620+t.rng()*320;a.position.set(Math.cos(l)*c*.35,(t.rng()-.5)*160,Math.sin(l)*c);const h=24+this.wave*3+t.rng()*14,d=new w((t.rng()-.5)*60,(t.rng()-.5)*10,(t.rng()-.5)*30).sub(a.position).normalize().multiplyScalar(h);this.group.add(a),this.asteroids.push({mesh:a,velocity:d,radius:i,hp:Math.max(1,Math.round(i/4)),alive:!0})}}update(e,t){if(this.ended)return;this.elapsed+=e,this.waveTimer+=e,this.fireCooldown=Math.max(0,this.fireCooldown-e),this.waveTimer>x2&&(this.waveTimer=0,this.wave+=1,t.audio.alarm(),t.toast("第 "+this.wave+" 波小行星接近！","warn"),this.spawnWave(2+this.wave));const n=t.camera;n.position.set(46,12.4,26),n.rotation.set(this.pitch,this.yaw,0,"YXZ");for(const i of this.asteroids){if(!i.alive)continue;i.mesh.position.addScaledVector(i.velocity,e),i.mesh.rotation.x+=e*.4,i.mesh.rotation.y+=e*.3;const r=i.mesh.position;r.x>Hi.minX-i.radius&&r.x<Hi.maxX+i.radius&&r.y>Hi.minY-i.radius&&r.y<Hi.maxY+i.radius&&r.z>Hi.minZ-i.radius&&r.z<Hi.maxZ+i.radius&&(i.alive=!1,this.group?.remove(i.mesh),this.hull=Math.max(0,this.hull-_2),t.audio.explosion(),t.toast("舰体被击中！完整度 "+Math.round(this.hull/br*100)+"%","error"),this.hull<=0&&this.finish(!1))}for(const i of this.bolts){i.mesh.position.x+=i.velocity.x*e,i.mesh.position.y+=i.velocity.y*e,i.mesh.position.z+=i.velocity.z*e,i.life-=e;for(const r of this.asteroids)if(r.alive&&i.mesh.position.distanceTo(r.mesh.position)<r.radius+2.4){r.hp-=1,this.spawnBurst(r.mesh.position,r.radius),r.hp<=0?(r.alive=!1,this.group?.remove(r.mesh),this.destroyed+=1,this.score+=Math.round(r.radius*8),t.audio.explosion()):t.audio.laser(),i.life=0;break}i.life<=0&&this.group?.remove(i.mesh)}this.bolts=this.bolts.filter(i=>i.life>0);for(const i of this.bursts){i.life-=e;const r=i.points.geometry.attributes.position;for(let o=0;o<r.count;o+=1)r.setXYZ(o,r.getX(o)+i.velocities[o*3]*e,r.getY(o)+i.velocities[o*3+1]*e,r.getZ(o)+i.velocities[o*3+2]*e);r.needsUpdate=!0,i.points.material.opacity=Math.max(0,i.life/.8),i.life<=0&&this.group?.remove(i.points)}this.bursts=this.bursts.filter(i=>i.life>0),t.setHud({title:"舱外炮塔 · 第 "+this.wave+" 波",score:"得分 "+this.score+" · 击毁 "+this.destroyed,extra:"舰体完整度 "+Math.round(this.hull/br*100)+"%",hint:"左键开火 · Esc/E 退出"}),this.elapsed>180&&this.finish(!0)}spawnBurst(e,t){const n=this.ctx;if(!n||!this.group)return;const i=28,r=new Float32Array(i*3),o=new Float32Array(i*3);for(let c=0;c<i;c+=1){r[c*3]=e.x,r[c*3+1]=e.y,r[c*3+2]=e.z;const h=14+n.rng()*22;o[c*3]=(n.rng()-.5)*h,o[c*3+1]=(n.rng()-.5)*h,o[c*3+2]=(n.rng()-.5)*h}const a=new je;a.setAttribute("position",new kt(r,3));const l=new ol(a,new rl({color:16763024,size:Math.max(1.4,t*.12),transparent:!0,opacity:1,depthWrite:!1}));this.group.add(l),this.bursts.push({points:l,life:.8,velocities:o})}onPointerMove(e,t){this.yaw-=e*.0022,this.pitch=Math.max(-1.2,Math.min(1.2,this.pitch-t*.0022))}onPointerDown(){const e=this.ctx;if(!e||!this.group||this.fireCooldown>0)return;this.fireCooldown=.18;const t=new w;e.camera.getWorldDirection(t);const n=new ve(new et(.35,.35,6,8),new Ge({color:9433343}));n.position.copy(e.camera.position).addScaledVector(t,6),n.quaternion.setFromUnitVectors(new w(0,1,0),t),this.group.add(n),this.bolts.push({mesh:n,velocity:{x:t.x*420,y:t.y*420,z:t.z*420},life:2.4}),e.audio.laser()}finish(e){const t=this.ctx;if(!t||this.ended)return;this.ended=!0;const n=e?Math.round(this.hull*20):0,i=this.score+n;t.submitScore("turret",i,Math.round(this.elapsed*1e3),"击毁 "+this.destroyed+" 颗").then(r=>{t.finish({title:e?"炮塔演练完成":"舰体受损，演练终止",lines:["击毁小行星："+this.destroyed+" 颗",e?"完整度奖励：+"+n:"完整度："+Math.round(this.hull)+"%",r.ok?"本次得分 "+i+"，历史最佳 "+(r.best??i)+"，排名第 "+(r.rank??1):"成绩未能保存："+(r.error||"未知原因")],score:i,canRetry:!0})})}dispose(e){this.group&&(e.scene.remove(this.group),this.group.traverse(t=>{const n=t;n.geometry&&n.geometry.dispose()})),this.group=null,this.asteroids=[],this.bolts=[],this.bursts=[],this.ctx=null}}du(new y2);const $e=6,gn=4,Wo=75,wt=[1,2,4,8];class M2{id="repair";name="损管抢修";description="太阳核心回路被震断，限时把电力接到各个系统。";icon="wrench";mode="screen";ctx=null;cells=[];targets=[];timeLeft=Wo;round=1;score=0;elapsed=0;solved=!1;failed=!1;hint="点击导线旋转，把电力从左侧堆芯引到右侧系统接口。";lastTick=0;start(e){this.ctx=e,this.round=1,this.score=0,this.elapsed=0,this.buildRound(),e.setHud(null)}buildRound(){const e=this.ctx;if(!e)return;this.timeLeft=Math.max(35,Wo-(this.round-1)*10),this.solved=!1,this.failed=!1;const t=e.rng.bind(e),n=[];let i=Math.floor(t()*gn);for(let u=0;u<$e;u+=1)if(n.push([u,i]),u<$e-1&&t()>.45){const d=i===0?1:i===gn-1?-1:t()>.5?1:-1;n.push([u,i+d]),i+=d}this.cells=[];for(let u=0;u<$e*gn;u+=1)this.cells.push({mask:0,fixed:!1,powered:!1});const r=(u,d)=>{const f=this.cells[u[1]*$e+u[0]],g=this.cells[d[1]*$e+d[0]];u[1]>d[1]&&(f.mask|=wt[0]),u[0]<d[0]&&(f.mask|=wt[1]),u[1]<d[1]&&(f.mask|=wt[2]),u[0]>d[0]&&(f.mask|=wt[3]),d[1]<u[1]&&(g.mask|=wt[0]),d[0]>u[0]&&(g.mask|=wt[1]),d[1]>u[1]&&(g.mask|=wt[2]),d[0]<u[0]&&(g.mask|=wt[3])},o=this.cells[n[0][1]*$e+0];o.mask|=wt[3],o.fixed=!0;for(let u=0;u<n.length-1;u+=1)r(n[u],n[u+1]);const a=n[n.length-1];this.cells[a[1]*$e+($e-1)].mask|=wt[1],this.targets=[a[1]*$e+($e-1)];const l=(a[1]+2)%gn,c=$e-1,h=l*$e+c;this.targets.includes(h)||(this.cells[h].mask|=wt[1],this.targets.push(h));for(const u of this.cells){if(u.mask===0)continue;const d=Math.floor(t()*4);u.mask=Xo(u.mask,d)}this.cells[n[0][1]*$e].mask=Xo(this.cells[n[0][1]*$e].mask,0),this.cells[n[0][1]*$e].mask|=wt[3]}computePower(){for(const t of this.cells)t.powered=!1;const e=[];for(let t=0;t<gn;t+=1){const n=t*$e;this.cells[n].mask&wt[3]&&(this.cells[n].powered=!0,e.push(n))}for(;e.length>0;){const t=e.shift(),n=t%$e,i=Math.floor(t/$e),r=this.cells[t].mask,o=[[0,-1,wt[0],wt[2]],[1,0,wt[1],wt[3]],[0,1,wt[2],wt[0]],[-1,0,wt[3],wt[1]]];for(const[a,l,c,h]of o){if(!(r&c))continue;const u=n+a,d=i+l;if(u<0||u>=$e||d<0||d>=gn)continue;const f=d*$e+u;this.cells[f].mask&h&&(this.cells[f].powered||(this.cells[f].powered=!0,e.push(f)))}}return this.targets.every(t=>this.cells[t].powered)}update(e,t){this.solved||this.failed||(this.elapsed+=e,this.timeLeft-=e,this.timeLeft<=0&&(this.failed=!0,t.audio.alarm(),t.submitScore("repair",this.score,Math.round(this.elapsed*1e3),"第 "+this.round+" 轮超时").then(n=>{t.finish({title:"抢修超时",lines:["完成轮数："+(this.round-1),"本次得分："+this.score,n.ok?"历史最佳 "+(n.best??this.score):"成绩未保存："+(n.error||"")],score:this.score,canRetry:!0})})),this.timeLeft<10&&performance.now()-this.lastTick>1e3&&(this.lastTick=performance.now(),t.audio.alarm()))}draw(e,t){e.panel({x:20,y:130,w:40+$e*118+20,h:gn*118+60},{title:"电力回路 / CIRCUIT"});for(let a=0;a<gn;a+=1)for(let l=0;l<$e;l+=1){const c=a*$e+l,h=this.cells[c],u=40+l*118,d=150+a*118,f={x:u+6,y:d+6,w:106,h:106},g=this.targets.includes(c),x=e.isHovered("cell-"+c);e.ctx.fillStyle=h.powered?"rgba(80, 220, 160, 0.22)":x?"rgba(90, 150, 200, 0.22)":"rgba(14, 28, 40, 0.6)",e.ctx.fillRect(f.x,f.y,f.w,f.h),e.ctx.strokeStyle=g?e.theme.warn:"rgba(90, 150, 190, 0.45)",e.ctx.lineWidth=g?3:1.5,e.ctx.strokeRect(f.x+.5,f.y+.5,f.w-1,f.h-1);const p=f.x+f.w/2,m=f.y+f.h/2,_=f.w*.32,v=h.powered?e.theme.ok:"rgba(150, 190, 220, 0.55)";if(e.ctx.strokeStyle=h.powered?e.theme.ok:v,e.ctx.lineWidth=9,e.ctx.lineCap="round",[[p,m,p,m-_],[p,m,p+_,m],[p,m,p,m+_],[p,m,p-_,m]].forEach((S,E)=>{h.mask&wt[E]&&(e.ctx.beginPath(),e.ctx.moveTo(S[0],S[1]),e.ctx.lineTo(S[2],S[3]),e.ctx.stroke())}),e.ctx.beginPath(),e.ctx.arc(p,m,6,0,Math.PI*2),e.ctx.fillStyle=h.powered?e.theme.ok:v,e.ctx.fill(),h.powered){const S=.5+.5*Math.sin(performance.now()/200+c);e.ctx.globalAlpha=.25*S,e.ctx.fillStyle=e.theme.ok,e.ctx.fillRect(f.x,f.y,f.w,f.h),e.ctx.globalAlpha=1}}e.panel({x:40+$e*118+40,y:130,w:230,h:gn*118+60},{title:"抢修进度 / STATUS"}),e.text(40+$e*118+64,190,"剩余时间",{size:16,color:e.theme.textDim}),e.text(40+$e*118+64,232,Math.max(0,this.timeLeft).toFixed(1)+" s",{size:30,weight:"bold",color:this.timeLeft<15?e.theme.error:e.theme.text}),e.progress({x:40+$e*118+64,y:250,w:182,h:14},this.timeLeft/Wo,{color:this.timeLeft<15?e.theme.error:e.theme.accent,showValue:!1});const o=this.targets.filter(a=>this.cells[a].powered).length;e.text(40+$e*118+64,310,"已接通系统",{size:16,color:e.theme.textDim}),e.text(40+$e*118+64,350,o+" / "+this.targets.length,{size:30,weight:"bold"}),e.text(40+$e*118+64,400,"当前轮次",{size:16,color:e.theme.textDim}),e.text(40+$e*118+64,436,String(this.round),{size:28,weight:"bold",color:e.theme.accent}),e.text(40+$e*118+64,500,"得分 "+this.score,{size:20,color:e.theme.accent}),e.text(40,150+gn*118+30,this.hint,{size:15,color:e.theme.textDim})}onScreenClick(e){const r=Math.floor((e.cursor.x-40)/118),o=Math.floor((e.cursor.y-150)/118);if(r<0||r>=$e||o<0||o>=gn)return;const a=o*$e+r,l=this.cells[a];if(!(!l||l.mask===0)&&(l.mask=Xo(l.mask,1),this.ctx?.audio.chime("repair"),this.computePower())){this.solved=!0;const c=Math.round(this.timeLeft*40+500);this.score+=c,this.ctx?.toast("回路接通！本轮 +"+c+" 分","ok"),window.setTimeout(()=>{const h=this.ctx;h&&(this.round+=1,this.round>3?h.submitScore("repair",this.score,Math.round(this.elapsed*1e3),"完成 3 轮抢修").then(u=>{h.finish({title:"抢修完成",lines:["完成轮数：3","剩余时间奖励已计入",u.ok?"本次得分 "+this.score+"，历史最佳 "+(u.best??this.score)+"，排名第 "+(u.rank??1):"成绩未保存："+(u.error||"")],score:this.score,canRetry:!0})}):this.buildRound())},900)}}}function Xo(s,e){let t=s;for(let n=0;n<(e%4+4)%4;n+=1)t=(t<<1|t>>3)&15;return t}const b2=new M2;du(b2);class T2{constructor(e,t,n,i){this.container=e,this.hudRoot=t,this.bootstrap=n,this.qualityLevel=xu(n.quality);const r=Vs[this.qualityLevel];Object.assign(this.quality,r),this.jumpIntervalMinutes=n.jump_interval_minutes,this.renderer=new zg({canvas:i,antialias:r.antialias,powerPreference:"high-performance",logarithmicDepthBuffer:!0}),this.renderer.setPixelRatio(Math.min(window.devicePixelRatio,r.pixelRatio)),this.renderer.setSize(e.clientWidth,Math.max(1,e.clientHeight),!1),this.renderer.outputColorSpace=Ft,this.renderer.shadowMap.enabled=this.qualityLevel!=="low",this.renderer.shadowMap.type=ch,this.renderer.toneMapping=Wr,this.renderer.toneMappingExposure=.95,this.renderer.setClearColor(198155,1),this.camera=new Jt(54,e.clientWidth/Math.max(1,e.clientHeight),.1,Jc),this.camera.layers.enable(1),this.orbit=new P1(this.camera,i),this.orbit.enabled=!1,this.orbit.enableDamping=!0,this.orbit.enablePan=!1,this.orbit.minDistance=120,this.orbit.maxDistance=Cs.length*4,this.hud=new tv(t,th(Ha).instruments),this.hud.setShipIdentity(this.shipName),this.hud.attach(this.camera),this.input=new pv(i),this.audio=new H1(n.enable_audio),this.shell.playerName=this.playerName,this.ship=th(Ha).build(this.scene,this.collision,l=>this.hud.toast(l,"info",1200)),this.materials=this.ship.materials,this.ship.group.traverse(l=>{l.userData.exteriorOnly&&this.exteriorLights.push(l)}),this.ship.setName(this.shipName),this.decoration=Vx(this.scene,this.collision,this.materials,this.ship.rooms),this.ship.group.add(this.decoration),this.decoration.traverse(l=>{l instanceof ve&&(l.castShadow=!0,l.receiveShadow=!0)}),this.player=new bv(this.ship.ladders),this.player.spawn(this.ship.spawn,this.ship.spawnYaw),this.space=new $c(this.scene,this.camera,{quality:r}),this.rendering=new fv(this.renderer,this.scene,this.camera,this.qualityLevel),this.rendering.resize(e.clientWidth,Math.max(1,e.clientHeight)),this.systemIndex=Math.floor(Math.random()*1e3),this.warpCountdown=this.nextWarpDelay(),this.buildTerminals();for(const l of this.terminals){const c=new Set(l.solidMeshes());this.collision.addStaticMesh(l.group,{tag:"console",owner:l.anchor.spec.id,filter:h=>c.has(h)})}for(const l of this.terminals)l.group.traverse(c=>{c instanceof ve&&c.material instanceof Ke&&!c.material.transparent&&(c.castShadow=!0,c.receiveShadow=!0)});const o=new Set(Object.values(this.materials)),a=new Set;this.scene.traverse(l=>{const c=l;for(const h of c.material?Array.isArray(c.material)?c.material:[c.material]:[])h instanceof Ke&&!o.has(h)&&!a.has(h)&&h.metalness>.35&&(Os(h,{roughnessVariation:.035,colourVariation:.015,relief:0}),h.envMapIntensity=.52,a.add(h))}),this.input.onNextClick(()=>{this.mode==="world"&&!this.pausedOverlay&&!this.hud.hasModal&&(this.audio.resume(),this.input.requestLock())}),this.input.onLockLost=()=>{this.mode==="world"&&this.booted&&this.showPauseOverlay()},window.addEventListener("resize",this.handleResize),document.addEventListener("visibilitychange",this.handleVisibility),window.addEventListener("keydown",this.handleKeyDown,!0),window.__neobotStarship=this}scene=new kg;camera;collision=new Q1;shell=new lx;hud;input;textCapture=new cx;materials;quality={...Vs.medium};actions=this;jumpIntervalMinutes;qualityLevel;renderer;rendering;orbit;decoration;shipName=_u();ship;exteriorLights=[];space;player;terminals=[];audio;raycaster=new hl;clockLast=0;rafId=0;running=!1;visible=!0;mode="boot";focused=null;candidate=null;focusBlend=0;focusFrom=new w;focusLook=new w;currentLook=new w;boosts=new Map;unlocked=new Set;statusPoller=null;warpCountdown=0;seated=!1;systemIndex=0;fpsAccumulator=0;fpsFrames=0;fps=0;activeMinigame=null;minigameStation=null;minigameScreenMode=!1;minigameStartedAt=0;playerName=yu();pausedOverlay=!1;minigameContext=null;savedView=null;booted=!1;disposed=!1;start(){this.running||(this.running=!0,this.booted=!0,this.mode="world",this.clockLast=performance.now(),this.statusPoller=new dt(()=>hs.get("/api/status"),5e3,e=>this.applyStatus(e),()=>{}),this.statusPoller.start(!0),this.rafId=requestAnimationFrame(this.frame),this.hud.toast("欢迎登舰，"+this.playerName+"。WASD 移动，走近终端按 E 使用，Esc 打开菜单。","info",7e3))}dispose(){if(!this.disposed){this.disposed=!0,this.running=!1,cancelAnimationFrame(this.rafId),this.statusPoller?.stop(),this.stopMinigameModule(),this.space.dispose();for(const e of this.terminals)e.dispose();this.collision.clear(),this.ship.dispose(),this.orbit.dispose(),this.hud.dispose(),this.closePauseOverlay(),this.input.dispose(),this.textCapture.dispose(),this.audio.dispose(),window.removeEventListener("resize",this.handleResize),document.removeEventListener("visibilitychange",this.handleVisibility),window.removeEventListener("keydown",this.handleKeyDown,!0),this.rendering.dispose(),this.renderer.dispose()}}handleResize=()=>{const e=Math.max(1,this.container.clientWidth),t=Math.max(1,this.container.clientHeight);this.renderer.setSize(e,t,!1),this.rendering.resize(e,t),this.camera.aspect=e/t,this.camera.updateProjectionMatrix()};handleVisibility=()=>{this.visible=!document.hidden,this.visible?(this.clockLast=performance.now(),this.statusPoller?.start(!0),this.focused?.focus()):(this.statusPoller?.stop(),this.focused?.blur(),this.input.keys.clear())};handleKeyDown=e=>{const t=e.target;if(!(e.isComposing||t?.closest('input, textarea, select, [contenteditable="true"], .hud-dialog-overlay')||document.querySelector(".hud-dialog-overlay, dialog[open]"))&&!(this.pausedOverlay||this.hud.hasModal)&&!e.repeat){if(this.mode==="world"||this.mode==="exterior"){if(e.key.toLowerCase()==="h"){this.hud.group.visible=!this.hud.group.visible;return}const i={1:"bridge",2:"war-forge",3:"robot-forge",v:"exterior"}[e.key.toLowerCase()];if(i){this.visitSector(i),e.preventDefault();return}}if(this.mode==="exterior"){(e.key==="Escape"||e.key.toLowerCase()==="m")&&this.showPauseOverlay();return}if(this.mode==="minigame"&&this.activeMinigame&&!this.minigameScreenMode){if(e.key==="Escape"||e.key==="e"||e.key==="E"){this.exitMinigame("已被玩家终止"),e.preventDefault();return}this.activeMinigame.onKey?.(e.key,this.ensureMinigameContext());return}if(e.key==="Escape"){(this.mode==="terminal"||this.minigameScreenMode)&&(this.minigameScreenMode?this.exitMinigame("已被玩家终止"):this.blurTerminal(),e.preventDefault());return}if(e.key==="e"||e.key==="E"){this.minigameScreenMode?this.exitMinigame("已被玩家终止"):this.mode==="terminal"?this.blurTerminal():this.mode==="world"&&this.interact();return}if(e.key==="f"||e.key==="F"){this.mode==="world"&&this.toggleSeat();return}(e.key==="m"||e.key==="M")&&this.mode==="world"&&!this.pausedOverlay&&this.showPauseOverlay()}};buildTerminals(){const e=new Map;for(const t of g2())e.set(t.id,t);for(const t of this.ship.anchors.values()){const n=t.spec.target,i=e.get(n);if(!i||t.spec.kind==="minigame"&&i.id!==n)continue;const r=new Mx(i,this,t);this.terminals.push(r)}this.applyStatusAvailability()}applyStatusAvailability(){for(const e of this.terminals)e.setAvailability(this.shell.availability(e.definition.id))}toast(e,t="info"){this.hud.toast(e,t)}confirm(e){return this.hud.confirm(e)}openMinigame(e,t){const n=t?this.terminals.find(i=>i.anchor.spec.id===t)??null:null;this.startMinigame(e,n)}get consoleApi(){return Mu}get gameApi(){return hs}requestRedraw(){for(const e of this.terminals)e.markDirty()}triggerWarp(e,t){if(this.space.warping)return!1;const n=this.space.triggerWarp(()=>{this.systemIndex=t===void 0?this.systemIndex+1:t,this.hud.toast("已抵达新星系："+this.systemName(),"ok",5e3),this.unlockAchievement("first-jump",e?"手动跃迁":"自动跃迁")});return n&&(this.audio.warp(),this.hud.setBanner("跃迁引擎点火 · 全舰注意","info"),window.setTimeout(()=>{!this.space.warping&&!this.shell.status.standby&&this.hud.setBanner(null)},4200)),n}warping(){return this.space.warping}warpPhase(){return this.space.warpPhase}systemName(){const e=["天鹅座 λ-4","猎户悬臂 K-17","南门二 β","天苑四 ε","蛇夫座 9","武仙座 τ","船底座 HD-7","仙女座 M31-附","半人马 ζ","天琴座 Vega-2"];return e[this.systemIndex%e.length]}playChime(e){this.audio.chime(e)}playMusic(e){this.audio.playMusic(e)}stopMusic(){this.audio.stopMusic()}setMusicActive(e){e||this.audio.stopMusic()}boost(e,t){this.boosts.set(e,{remaining:t})}boostRemaining(e){return this.boosts.get(e)?.remaining??0}unlockAchievement(e,t=""){this.unlocked.has(e)||(this.unlocked.add(e),hs.post("/api/achievements",{key:e,detail:t}))}setSeated(e){this.seated=e,this.player.velocity.set(0,0,0)}isSeated(){return this.seated}lookAtTarget(e){const t={主行星:new w(-520,220,-1700),伴星卫星:new w(900,180,1200),小行星带:new w(-600,120,900),航道上的货船:new w(400,60,-500)},i=(t[e]||t.主行星).clone().sub(this.camera.position).normalize();this.player.yaw=Math.atan2(-i.x,-i.z),this.player.pitch=Math.asin(_t.clamp(i.y,-1,1)),this.hud.toast("望远镜已对准："+e,"info")}zoomView(e){this.camera.fov=Math.max(18,Math.min(96,this.camera.fov/e)),this.camera.updateProjectionMatrix()}visitSector(e){if(this.activeMinigame){this.hud.toast("请先结束当前演练","warn");return}if(this.focused&&(this.focused.blur(),this.focused=null),this.closePauseOverlay(),this.textCapture.close(),this.seated=!1,this.input.keys.clear(),this.camera.fov=60,this.camera.updateProjectionMatrix(),e==="exterior"&&this.mode!=="exterior"||e==="exterior-close"||e==="exterior-full"){if(this.mode="exterior",this.input.mode="menu",this.input.releaseLock(),this.camera.near=.1,this.camera.fov=e==="exterior-close"?50:44,this.camera.updateProjectionMatrix(),e==="exterior-close")this.orbit.target.set(0,0,8),this.camera.position.set(170,95,-240);else{const i=this.ship.hullBounds.getCenter(new w);this.orbit.target.copy(i),this.camera.position.copy(i).add(new w(.4,.46,-.74).multiplyScalar(Cs.length*Math.max(1,1.35/this.camera.aspect)))}this.orbit.enabled=!0,this.orbit.update();return}const n={bridge:[0,.08,-11.5,0],"war-forge":[-7,.08,18,2.25],"robot-forge":[7,.08,18,-2.5],reactor:[0,.08,82,Math.PI],archive:[29,.08,87,-Math.PI/2]}[e];this.mode="world",this.input.mode="world",this.orbit.enabled=!1,n&&this.player.spawn(new w(n[0],n[1],n[2]),n[3]),e==="robot-forge"&&(this.player.pitch=.16),e==="reactor"&&(this.player.pitch=.43),this.camera.near=.1,this.camera.fov=54,this.camera.updateProjectionMatrix(),this.camera.position.copy(this.player.eyePosition()),this.camera.rotation.set(this.player.pitch,this.player.yaw,0,"YXZ"),this.input.requestLock()}nextWarpDelay(){return this.jumpIntervalMinutes<=0?Number.POSITIVE_INFINITY:this.jumpIntervalMinutes*60*(.6+Math.random()*.7)}frame=e=>{if(this.rafId=requestAnimationFrame(this.frame),!this.visible){this.clockLast=e;return}const t=Math.min(.05,Math.max(0,(e-this.clockLast)/1e3));this.clockLast=e,this.fpsAccumulator+=t,this.fpsFrames+=1,this.fpsAccumulator>.5&&(this.fps=Math.round(this.fpsFrames/this.fpsAccumulator),this.fpsAccumulator=0,this.fpsFrames=0),this.updateBoosts(t),this.space.update(t),this.ship.group.userData.update?.(t,this.player.position,this.space.warping?1:.55),!this.pausedOverlay&&!this.hud.hasModal&&this.decoration.userData.update?.(t),this.hud.update(this.input.pointer,t),this.pausedOverlay||this.hud.hasModal||(this.mode==="exterior"?this.orbit.update():this.mode==="minigame"&&this.activeMinigame&&!this.minigameScreenMode?this.updateWorldMinigame(t):this.focused&&(this.mode==="terminal"||this.mode==="minigame")?this.updateFocusedTerminal(t):this.updateWorld(t));for(const n of this.terminals)n!==this.focused&&n.update(t);this.focused?.update(t),this.updateHud();for(const n of this.exteriorLights)n.visible=this.mode==="exterior";this.rendering.render(t),this.input.endFrame()};updateBoosts(e){for(const[t,n]of this.boosts)n.remaining-=e,n.remaining<=0&&this.boosts.delete(t)}updateWorld(e){const t=this.input.locked,n=this.boostRemaining("sprint")>0?1.25:1;this.player.update(e,this.collision,this.input,{enabled:t&&!this.seated,speedScale:n,jumpScale:this.boostRemaining("jump")>0?1.15:1,onStep:i=>this.audio.footstep(i)}),this.camera.position.copy(this.player.eyePosition()),this.seated&&(this.camera.position.y-=.5),this.camera.rotation.set(this.player.pitch,this.player.yaw,0,"YXZ"),this.candidate=this.findCandidate(),this.updatePrompt(),!this.space.warping&&Number.isFinite(this.warpCountdown)&&(this.warpCountdown-=e,this.warpCountdown<=0&&(this.warpCountdown=this.nextWarpDelay(),this.triggerWarp(!1)&&this.hud.toast("舰载 AI 规划了一次自动跃迁。","info",4e3)))}updateFocusedTerminal(e){const t=this.focused;if(!t){this.mode="world";return}this.focusBlend=Math.min(1,this.focusBlend+e*4.5);const n=t.focusView(),i=w2(this.focusBlend);this.camera.position.lerpVectors(this.focusFrom,n.position,i),this.currentLook.copy(this.focusLook).lerp(n.target,i),this.camera.lookAt(this.currentLook),this.raycaster.setFromCamera(new Q(this.input.pointer.x,this.input.pointer.y),this.camera);const r=this.raycaster.intersectObject(t.screen.mesh,!1),o=r.length>0?r[0]:null;t.handlePointer(o,this.input.pointer.clicked&&!this.minigameScreenMode,this.input.pointer.wheel),this.input.pointer.clicked&&this.activeMinigame&&this.minigameScreenMode&&o?.uv&&this.activeMinigame.onScreenClick?.(t.ui,this.ensureMinigameContext()),this.activeMinigame&&this.minigameScreenMode&&(this.activeMinigame.update?.(e,this.ensureMinigameContext()),t.markDirty())}updateWorldMinigame(e){const t=this.activeMinigame;if(!t){this.mode="world";return}const n=this.ensureMinigameContext();t.update?.(e,n),(this.input.pointer.deltaX!==0||this.input.pointer.deltaY!==0)&&t.onPointerMove?.(this.input.pointer.deltaX,this.input.pointer.deltaY,n),this.input.pointer.clicked&&t.onPointerDown?.(n)}updateHud(){if(this.mode==="exterior"){this.hud.showPrompt(null),this.hud.setCrosshairVisible(!1),this.hud.setStatus([this.shipName+" · 舰体总览","实尺 74.4 km × 17.2 km × 9.1 km · 护航艇长 300 m","拖动旋转 · 滚轮缩放 · H 显隐仪表 · V 返回 · M 操作仪"]);return}if(this.mode==="terminal"){this.hud.setCrosshairVisible(!1);const r=this.minigameScreenMode?"演练中：点击操作 · E / Esc 退出":this.focused?.definition.id==="logs"?"日志终端 · 点击条目查看 · E / Esc 离开":"终端已聚焦 · 鼠标操作 · E / Esc 离开";this.hud.setStatus([r+" · "+this.fps+" FPS"]);return}if(this.mode==="minigame"){this.hud.setCrosshairVisible(!this.minigameScreenMode,"pointer");return}const e=Zv(this.ship.rooms,this.player.position),t=[];t.push((e?e.label:"舰内")+" · "+this.fps+" FPS");const n=this.space.warping?"跃迁中":"巡航";t.push((this.shell.status.standby?"低功耗待机":n+" · "+this.systemName())+" · 插件 "+this.shell.status.plugins.running+"/"+this.shell.status.plugins.total+(this.shell.status.online?" · 通讯正常":" · 通讯中断"));const i=[];this.boostRemaining("sprint")>0&&i.push("疾跑增益 "+this.boostRemaining("sprint").toFixed(0)+"s"),this.boostRemaining("jump")>0&&i.push("跳跃增益 "+this.boostRemaining("jump").toFixed(0)+"s"),i.length>0&&t.push(i.join(" · ")),this.input.locked?t.push("WASD 移动 · Shift 潜行 · Ctrl 疾跑 · 空格跳跃 · E 交互 · F 就座 · M 菜单"):t.push("点击画面继续操作 · M 打开菜单"),this.hud.setStatus(t),this.hud.setCrosshairVisible(this.input.locked&&!this.seated,this.candidate?"pointer":"dot")}findCandidate(){const e=this.camera.position,t=new w;this.camera.getWorldDirection(t);let n=null,i=0;for(const r of this.terminals){const o=r.operatingSurface.getWorldPosition(new w),a=o.clone().sub(e),l=a.length();if(l>4.2)continue;const c=o.clone().project(this.camera);if(c.z<-1||c.z>1||Math.abs(c.x)>1.15||Math.abs(c.y)>1.15)continue;const h=a.normalize().dot(t);if(h<.45||r.operatingSurface.getWorldDirection(new w).dot(e.clone().sub(o).normalize())<.08||this.collision.segmentBlocked(e,o,r.anchor.spec.id))continue;const f=h*2-l*.12;f>i&&(i=f,n=r)}return n}updatePrompt(){const e=this.candidate;if(!e){this.hud.showPrompt(null);return}const t=e.anchor.spec;if(!e.interactable){this.hud.showPrompt(t.label+" · E 查看离线状态（"+e.availabilityReason+"）");return}this.hud.showPrompt(t.label+" · "+t.hint)}interact(){const e=this.candidate;if(e){if(!e.interactable){this.focusTerminal(e),this.hud.toast("只读观察 · "+(e.availabilityReason||"终端离线"),"warn");return}if(e.definition.kind==="minigame"){this.startMinigame(e.definition.id,e);return}this.focusTerminal(e)}}focusTerminal(e){this.focused=e,this.mode="terminal",this.input.mode="terminal",this.input.releaseLock(),this.focusFrom.copy(this.camera.position),this.focusLook.copy(this.camera.position).add(new w(0,0,-1).applyQuaternion(this.camera.quaternion).multiplyScalar(8)),this.focusBlend=0,e.focus(),this.hud.showPrompt(null),this.audio.chime("terminal")}blurTerminal(){this.focused&&this.focused.blur(),this.focused=null,this.mode="world",this.input.mode="world",this.textCapture.close(),this.focusBlend=0,this.input.requestLock()}toggleSeat(){this.seated=!this.seated,this.hud.toast(this.seated?"已就座（按 F 起身）":"已起身","info")}startMinigame(e,t){const n=uu.get(e);if(!n){this.hud.toast("该小游戏没有客户端模块（可能需要更新游戏前端）","warn");return}this.activeMinigame&&this.stopMinigameModule(),t||(t=this.terminals.find(r=>r.definition.id===e)??null),this.minigameStation=t,this.activeMinigame=n,this.minigameScreenMode=n.mode==="screen",this.minigameStartedAt=performance.now(),this.savedView={position:this.player.position.clone(),yaw:this.player.yaw,pitch:this.player.pitch};const i=this.ensureMinigameContext();if(n.start?.(i),n.mode==="world"){const r=n.viewpoint?.(i);r&&(this.player.yaw=r.yaw,this.player.pitch=r.pitch,this.camera.position.copy(r.position),this.camera.rotation.set(r.pitch,r.yaw,0,"YXZ")),this.mode="minigame",this.input.mode="minigame",this.input.requestLock(),this.hud.showPrompt(null),this.audio.alarm()}else{if(this.mode="minigame",this.input.mode="terminal",t)this.focused=t,this.focusFrom.copy(this.camera.position),this.focusLook.copy(this.camera.position),this.focusBlend=0,t.setOverride((r,o)=>n.draw?.(r,this.ensureMinigameContext())??void 0),t.focus();else{this.hud.toast("未找到演练终端（"+e+"），已取消","warn"),this.activeMinigame=null,this.mode="world";return}this.input.releaseLock()}this.hud.toast("进入演练："+n.name+" · "+n.description,"ok",5e3)}ensureMinigameContext(){return this.minigameContext?this.minigameContext:(this.minigameContext={scene:this.scene,camera:this.camera,input:this.input,hud:this.hud,audio:this.audio,shell:this.shell,quality:this.quality,actions:this,playerPosition:this.player.position,submitScore:async(e,t,n,i)=>{const r=await hs.post("/api/scores",{game:e,score:t,duration_ms:n,detail:i,player:this.playerName});return r.ok?{ok:!0,best:r.data?.best,rank:r.data?.rank}:{ok:!1,error:r.error||"保存失败"}},leaderboard:(e,t)=>hs.get("/api/scores?game="+encodeURIComponent(e)+"&limit="+t),toast:(e,t)=>this.hud.toast(e,t||"info"),exit:e=>this.exitMinigame(e||"演练结束"),finish:e=>this.finishMinigame(e),setHud:e=>this.hud.setMinigame(e),rng:()=>Math.random()},this.minigameContext)}finishMinigame(e){this.hud.setMinigame(null);const t=this.activeMinigame?.id??"";this.hud.confirm({title:e.title,body:e.lines.join(`
`)+`

本次得分：`+e.score,confirmLabel:e.canRetry?"再来一局":"结束",cancelLabel:"返回舰内"}).then(n=>{const i=this.minigameStation;n&&t?(this.stopMinigameModule(),this.startMinigame(t,i)):this.exitMinigame("演练结束")})}stopMinigameModule(){this.activeMinigame&&(this.activeMinigame.dispose?.(this.ensureMinigameContext()),this.activeMinigame=null),this.minigameStation?.setOverride(null)}exitMinigame(e){if(!this.activeMinigame&&this.mode!=="minigame")return;const t=this.activeMinigame?.id;this.stopMinigameModule(),this.hud.setMinigame(null),this.minigameStation&&this.minigameStation.blur(),this.minigameStation=null,this.minigameScreenMode=!1,this.focused=null,this.mode="world",this.input.mode="world",this.savedView?(this.player.spawn(this.savedView.position,this.savedView.yaw),this.player.pitch=this.savedView.pitch,this.savedView=null):this.player.spawn(this.ship.spawn,this.ship.spawnYaw),this.camera.fov=54,this.camera.updateProjectionMatrix(),this.input.requestLock(),this.hud.toast("已返回舰内（"+e+"）","info"),t&&this.unlockAchievement("minigame-"+t,"完成一次演练")}applyStatus(e){this.shell.update(e),this.applyStatusAvailability(),this.requestRedraw(),e.standby?this.hud.setBanner("舰船处于低功耗待机："+(e.reason||"未说明原因")+" · 可在主控台恢复运行","warn"):this.hud.setBanner(null)}showPauseOverlay(){this.pausedOverlay||this.hud.hasModal||(this.pausedOverlay=!0,this.input.mode="menu",this.input.keys.clear(),this.orbit.enabled=!1,this.input.releaseLock(),this.hud.menu(this.shipName+" / 舰载操作仪",[{label:"继续探索",value:"resume"},{label:"74.4km 全舰",value:"exterior-full"},{label:"命名战舰",value:"ship-name"},{label:"01 星穹舰桥",value:"bridge"},{label:"02 战争机械",value:"war-forge"},{label:"03 机器人",value:"robot-forge"},{label:"04 太阳核心",value:"reactor"},{label:"05 记忆资料室",value:"archive"},{label:"画质 · "+Vs[this.qualityLevel].label,value:"quality"},{label:"灵敏度 · "+this.input.sensitivity,value:"sens"},{label:"视角 · "+(this.input.invertY?"反转":"正常"),value:"invert"},{label:"舰桥外侧尺度",value:"exterior-close"},{label:"舰长铭文",value:"name"},{label:"返回控制台",value:"console"}],"WASD 移动 · E 使用装置 · 1/2/3 区域 · V 舰体 · M 操作仪").then(async e=>{if(this.disposed)return;const t=e==="ship-name"||e==="name";if(t||this.closePauseOverlay(),t){this.input.mode="menu",this.pausedOverlay=!0,this.orbit.enabled=!1;const n=e==="ship-name",i=await this.hud.ask({title:n?"战舰铭文":"舰长铭文",value:n?this.shipName:this.playerName,hint:n?"1–24 个字符 · 仅保存在当前浏览器":"舰长姓名 · 与战舰名称独立",validate:r=>{const o=Array.from(r.trim()).length;return o<1||o>(n?24:32)?"请输入 1–"+(n?24:32)+" 个字符":null}});if(this.disposed)return;i!==null&&(n?(this.shipName=bu(i),this.ship.setName(this.shipName),this.hud.setShipIdentity(this.shipName),document.title=this.shipName+" · NeoBot 星舰"):(this.playerName=i.trim(),wu(this.playerName),this.shell.playerName=this.playerName)),this.closePauseOverlay(),this.showPauseOverlay()}else if(e==="quality"){const n=["low","medium","high"];this.applyQuality(n[(n.indexOf(this.qualityLevel)+1)%3]),this.showPauseOverlay()}else e==="sens"?(this.input.sensitivity=this.input.sensitivity>=2?.5:this.input.sensitivity+.5,this.showPauseOverlay()):e==="invert"?(this.input.invertY=!this.input.invertY,this.showPauseOverlay()):e==="console"?window.location.href=new URL("../",window.location.href).toString():e&&e!=="resume"?this.visitSector(e):this.mode!=="exterior"&&this.hud.toast("点击舰桥接管视角 · M 再次打开操作仪","info")}))}closePauseOverlay(){this.pausedOverlay=!1,this.input.mode=this.mode==="exterior"?"menu":"world",this.orbit.enabled=this.mode==="exterior"}applyQuality(e){this.qualityLevel=e,this.renderer.shadowMap.enabled=e!=="low",Su(e);const t=Vs[e];Object.assign(this.quality,t),this.renderer.setPixelRatio(Math.min(window.devicePixelRatio,t.pixelRatio)),this.rendering.updateQuality(e),this.rendering.resize(this.container.clientWidth,Math.max(1,this.container.clientHeight)),this.camera.far=Jc,this.camera.updateProjectionMatrix(),this.space.dispose(),this.space=new $c(this.scene,this.camera,{quality:t}),this.hud.toast("画质已切换为「"+t.label+"」","ok")}}function w2(s){return 1-Math.pow(1-s,3)}export{T2 as Game};
