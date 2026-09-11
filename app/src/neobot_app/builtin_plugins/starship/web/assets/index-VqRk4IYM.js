(function(){const t=document.createElement("link").relList;if(t&&t.supports&&t.supports("modulepreload"))return;for(const s of document.querySelectorAll('link[rel="modulepreload"]'))n(s);new MutationObserver(s=>{for(const r of s)if(r.type==="childList")for(const a of r.addedNodes)a.tagName==="LINK"&&a.rel==="modulepreload"&&n(a)}).observe(document,{childList:!0,subtree:!0});function e(s){const r={};return s.integrity&&(r.integrity=s.integrity),s.referrerPolicy&&(r.referrerPolicy=s.referrerPolicy),s.crossOrigin==="use-credentials"?r.credentials="include":s.crossOrigin==="anonymous"?r.credentials="omit":r.credentials="same-origin",r}function n(s){if(s.ep)return;s.ep=!0;const r=e(s);fetch(s.href,r)}})();const hr={low:{label:"节能",pixelRatio:.85,antialias:!1,asteroidCount:90,trafficCount:2,starCount:2200,particles:220,viewDistance:1400,fogDensity:.0016,refreshIdleTerminals:!1},medium:{label:"标准",pixelRatio:1,antialias:!0,asteroidCount:200,trafficCount:4,starCount:4200,particles:420,viewDistance:2200,fogDensity:.0011,refreshIdleTerminals:!1},high:{label:"高画质",pixelRatio:1.5,antialias:!0,asteroidCount:340,trafficCount:7,starCount:7200,particles:720,viewDistance:3200,fogDensity:8e-4,refreshIdleTerminals:!0}},Al="neobot-starship-quality",Rl="neobot-starship-player";function Mc(i){const t=localStorage.getItem(Al);return t==="low"||t==="medium"||t==="high"?t:i}function yc(i){localStorage.setItem(Al,i)}function Sc(){return localStorage.getItem(Rl)||"舰长"}function wc(i){localStorage.setItem(Rl,i.slice(0,32))}function Cl(){return new URL("../",window.location.href).pathname.replace(/\/+$/,"")}function ks(){return Cl()}function ur(){return window.location.pathname.replace(/\/+$/,"")}function Ec(){return Cl()+"/"}/**
 * @license
 * Copyright 2010-2024 Three.js Authors
 * SPDX-License-Identifier: MIT
 */const Na="169",bc=0,ao=1,Tc=2,Pl=1,Ac=2,_n=3,hn=0,Pe=1,de=2,Ln=0,Ei=1,Ai=2,oo=3,lo=4,Rc=5,qn=100,Cc=101,Pc=102,Lc=103,Dc=104,Ic=200,Uc=201,Nc=202,Fc=203,qr=204,Kr=205,Oc=206,Bc=207,kc=208,zc=209,Hc=210,Gc=211,Vc=212,Wc=213,Xc=214,jr=0,Zr=1,$r=2,Ri=3,Jr=4,Qr=5,ta=6,ea=7,Ll=0,Yc=1,qc=2,Dn=0,Kc=1,jc=2,Zc=3,Dl=4,$c=5,Jc=6,Qc=7,Il=300,Ci=301,Pi=302,na=303,ia=304,nr=306,ss=1e3,xn=1001,sa=1002,Ue=1003,th=1004,ds=1005,We=1006,dr=1007,jn=1008,Mn=1009,Ul=1010,Nl=1011,rs=1012,Fa=1013,Zn=1014,cn=1015,os=1016,Oa=1017,Ba=1018,Li=1020,Fl=35902,Ol=1021,Bl=1022,rn=1023,kl=1024,zl=1025,bi=1026,Di=1027,ka=1028,za=1029,Hl=1030,Ha=1031,Ga=1033,zs=33776,Hs=33777,Gs=33778,Vs=33779,ra=35840,aa=35841,oa=35842,la=35843,ca=36196,ha=37492,ua=37496,da=37808,fa=37809,pa=37810,ma=37811,ga=37812,_a=37813,xa=37814,va=37815,Ma=37816,ya=37817,Sa=37818,wa=37819,Ea=37820,ba=37821,Ws=36492,Ta=36494,Aa=36495,Gl=36283,Ra=36284,Ca=36285,Pa=36286,eh=3200,nh=3201,Vl=0,ih=1,Cn="",je="srgb",In="srgb-linear",Va="display-p3",ir="display-p3-linear",Ks="linear",se="srgb",js="rec709",Zs="p3",ni=7680,co=519,sh=512,rh=513,ah=514,Wl=515,oh=516,lh=517,ch=518,hh=519,ho=35044,uh=35048,uo="300 es",vn=2e3,$s=2001;class Ni{addEventListener(t,e){this._listeners===void 0&&(this._listeners={});const n=this._listeners;n[t]===void 0&&(n[t]=[]),n[t].indexOf(e)===-1&&n[t].push(e)}hasEventListener(t,e){if(this._listeners===void 0)return!1;const n=this._listeners;return n[t]!==void 0&&n[t].indexOf(e)!==-1}removeEventListener(t,e){if(this._listeners===void 0)return;const s=this._listeners[t];if(s!==void 0){const r=s.indexOf(e);r!==-1&&s.splice(r,1)}}dispatchEvent(t){if(this._listeners===void 0)return;const n=this._listeners[t.type];if(n!==void 0){t.target=this;const s=n.slice(0);for(let r=0,a=s.length;r<a;r++)s[r].call(this,t);t.target=null}}}const Se=["00","01","02","03","04","05","06","07","08","09","0a","0b","0c","0d","0e","0f","10","11","12","13","14","15","16","17","18","19","1a","1b","1c","1d","1e","1f","20","21","22","23","24","25","26","27","28","29","2a","2b","2c","2d","2e","2f","30","31","32","33","34","35","36","37","38","39","3a","3b","3c","3d","3e","3f","40","41","42","43","44","45","46","47","48","49","4a","4b","4c","4d","4e","4f","50","51","52","53","54","55","56","57","58","59","5a","5b","5c","5d","5e","5f","60","61","62","63","64","65","66","67","68","69","6a","6b","6c","6d","6e","6f","70","71","72","73","74","75","76","77","78","79","7a","7b","7c","7d","7e","7f","80","81","82","83","84","85","86","87","88","89","8a","8b","8c","8d","8e","8f","90","91","92","93","94","95","96","97","98","99","9a","9b","9c","9d","9e","9f","a0","a1","a2","a3","a4","a5","a6","a7","a8","a9","aa","ab","ac","ad","ae","af","b0","b1","b2","b3","b4","b5","b6","b7","b8","b9","ba","bb","bc","bd","be","bf","c0","c1","c2","c3","c4","c5","c6","c7","c8","c9","ca","cb","cc","cd","ce","cf","d0","d1","d2","d3","d4","d5","d6","d7","d8","d9","da","db","dc","dd","de","df","e0","e1","e2","e3","e4","e5","e6","e7","e8","e9","ea","eb","ec","ed","ee","ef","f0","f1","f2","f3","f4","f5","f6","f7","f8","f9","fa","fb","fc","fd","fe","ff"];let fo=1234567;const Qi=Math.PI/180,as=180/Math.PI;function Fi(){const i=Math.random()*4294967295|0,t=Math.random()*4294967295|0,e=Math.random()*4294967295|0,n=Math.random()*4294967295|0;return(Se[i&255]+Se[i>>8&255]+Se[i>>16&255]+Se[i>>24&255]+"-"+Se[t&255]+Se[t>>8&255]+"-"+Se[t>>16&15|64]+Se[t>>24&255]+"-"+Se[e&63|128]+Se[e>>8&255]+"-"+Se[e>>16&255]+Se[e>>24&255]+Se[n&255]+Se[n>>8&255]+Se[n>>16&255]+Se[n>>24&255]).toLowerCase()}function Ee(i,t,e){return Math.max(t,Math.min(e,i))}function Wa(i,t){return(i%t+t)%t}function dh(i,t,e,n,s){return n+(i-t)*(s-n)/(e-t)}function fh(i,t,e){return i!==t?(e-i)/(t-i):0}function ts(i,t,e){return(1-e)*i+e*t}function ph(i,t,e,n){return ts(i,t,1-Math.exp(-e*n))}function mh(i,t=1){return t-Math.abs(Wa(i,t*2)-t)}function gh(i,t,e){return i<=t?0:i>=e?1:(i=(i-t)/(e-t),i*i*(3-2*i))}function _h(i,t,e){return i<=t?0:i>=e?1:(i=(i-t)/(e-t),i*i*i*(i*(i*6-15)+10))}function xh(i,t){return i+Math.floor(Math.random()*(t-i+1))}function vh(i,t){return i+Math.random()*(t-i)}function Mh(i){return i*(.5-Math.random())}function yh(i){i!==void 0&&(fo=i);let t=fo+=1831565813;return t=Math.imul(t^t>>>15,t|1),t^=t+Math.imul(t^t>>>7,t|61),((t^t>>>14)>>>0)/4294967296}function Sh(i){return i*Qi}function wh(i){return i*as}function Eh(i){return(i&i-1)===0&&i!==0}function bh(i){return Math.pow(2,Math.ceil(Math.log(i)/Math.LN2))}function Th(i){return Math.pow(2,Math.floor(Math.log(i)/Math.LN2))}function Ah(i,t,e,n,s){const r=Math.cos,a=Math.sin,o=r(e/2),l=a(e/2),h=r((t+n)/2),d=a((t+n)/2),c=r((t-n)/2),u=a((t-n)/2),f=r((n-t)/2),g=a((n-t)/2);switch(s){case"XYX":i.set(o*d,l*c,l*u,o*h);break;case"YZY":i.set(l*u,o*d,l*c,o*h);break;case"ZXZ":i.set(l*c,l*u,o*d,o*h);break;case"XZX":i.set(o*d,l*g,l*f,o*h);break;case"YXY":i.set(l*f,o*d,l*g,o*h);break;case"ZYZ":i.set(l*g,l*f,o*d,o*h);break;default:console.warn("THREE.MathUtils: .setQuaternionFromProperEuler() encountered an unknown order: "+s)}}function vi(i,t){switch(t.constructor){case Float32Array:return i;case Uint32Array:return i/4294967295;case Uint16Array:return i/65535;case Uint8Array:return i/255;case Int32Array:return Math.max(i/2147483647,-1);case Int16Array:return Math.max(i/32767,-1);case Int8Array:return Math.max(i/127,-1);default:throw new Error("Invalid component type.")}}function Re(i,t){switch(t.constructor){case Float32Array:return i;case Uint32Array:return Math.round(i*4294967295);case Uint16Array:return Math.round(i*65535);case Uint8Array:return Math.round(i*255);case Int32Array:return Math.round(i*2147483647);case Int16Array:return Math.round(i*32767);case Int8Array:return Math.round(i*127);default:throw new Error("Invalid component type.")}}const Rh={DEG2RAD:Qi,RAD2DEG:as,generateUUID:Fi,clamp:Ee,euclideanModulo:Wa,mapLinear:dh,inverseLerp:fh,lerp:ts,damp:ph,pingpong:mh,smoothstep:gh,smootherstep:_h,randInt:xh,randFloat:vh,randFloatSpread:Mh,seededRandom:yh,degToRad:Sh,radToDeg:wh,isPowerOfTwo:Eh,ceilPowerOfTwo:bh,floorPowerOfTwo:Th,setQuaternionFromProperEuler:Ah,normalize:Re,denormalize:vi};class Ht{constructor(t=0,e=0){Ht.prototype.isVector2=!0,this.x=t,this.y=e}get width(){return this.x}set width(t){this.x=t}get height(){return this.y}set height(t){this.y=t}set(t,e){return this.x=t,this.y=e,this}setScalar(t){return this.x=t,this.y=t,this}setX(t){return this.x=t,this}setY(t){return this.y=t,this}setComponent(t,e){switch(t){case 0:this.x=e;break;case 1:this.y=e;break;default:throw new Error("index is out of range: "+t)}return this}getComponent(t){switch(t){case 0:return this.x;case 1:return this.y;default:throw new Error("index is out of range: "+t)}}clone(){return new this.constructor(this.x,this.y)}copy(t){return this.x=t.x,this.y=t.y,this}add(t){return this.x+=t.x,this.y+=t.y,this}addScalar(t){return this.x+=t,this.y+=t,this}addVectors(t,e){return this.x=t.x+e.x,this.y=t.y+e.y,this}addScaledVector(t,e){return this.x+=t.x*e,this.y+=t.y*e,this}sub(t){return this.x-=t.x,this.y-=t.y,this}subScalar(t){return this.x-=t,this.y-=t,this}subVectors(t,e){return this.x=t.x-e.x,this.y=t.y-e.y,this}multiply(t){return this.x*=t.x,this.y*=t.y,this}multiplyScalar(t){return this.x*=t,this.y*=t,this}divide(t){return this.x/=t.x,this.y/=t.y,this}divideScalar(t){return this.multiplyScalar(1/t)}applyMatrix3(t){const e=this.x,n=this.y,s=t.elements;return this.x=s[0]*e+s[3]*n+s[6],this.y=s[1]*e+s[4]*n+s[7],this}min(t){return this.x=Math.min(this.x,t.x),this.y=Math.min(this.y,t.y),this}max(t){return this.x=Math.max(this.x,t.x),this.y=Math.max(this.y,t.y),this}clamp(t,e){return this.x=Math.max(t.x,Math.min(e.x,this.x)),this.y=Math.max(t.y,Math.min(e.y,this.y)),this}clampScalar(t,e){return this.x=Math.max(t,Math.min(e,this.x)),this.y=Math.max(t,Math.min(e,this.y)),this}clampLength(t,e){const n=this.length();return this.divideScalar(n||1).multiplyScalar(Math.max(t,Math.min(e,n)))}floor(){return this.x=Math.floor(this.x),this.y=Math.floor(this.y),this}ceil(){return this.x=Math.ceil(this.x),this.y=Math.ceil(this.y),this}round(){return this.x=Math.round(this.x),this.y=Math.round(this.y),this}roundToZero(){return this.x=Math.trunc(this.x),this.y=Math.trunc(this.y),this}negate(){return this.x=-this.x,this.y=-this.y,this}dot(t){return this.x*t.x+this.y*t.y}cross(t){return this.x*t.y-this.y*t.x}lengthSq(){return this.x*this.x+this.y*this.y}length(){return Math.sqrt(this.x*this.x+this.y*this.y)}manhattanLength(){return Math.abs(this.x)+Math.abs(this.y)}normalize(){return this.divideScalar(this.length()||1)}angle(){return Math.atan2(-this.y,-this.x)+Math.PI}angleTo(t){const e=Math.sqrt(this.lengthSq()*t.lengthSq());if(e===0)return Math.PI/2;const n=this.dot(t)/e;return Math.acos(Ee(n,-1,1))}distanceTo(t){return Math.sqrt(this.distanceToSquared(t))}distanceToSquared(t){const e=this.x-t.x,n=this.y-t.y;return e*e+n*n}manhattanDistanceTo(t){return Math.abs(this.x-t.x)+Math.abs(this.y-t.y)}setLength(t){return this.normalize().multiplyScalar(t)}lerp(t,e){return this.x+=(t.x-this.x)*e,this.y+=(t.y-this.y)*e,this}lerpVectors(t,e,n){return this.x=t.x+(e.x-t.x)*n,this.y=t.y+(e.y-t.y)*n,this}equals(t){return t.x===this.x&&t.y===this.y}fromArray(t,e=0){return this.x=t[e],this.y=t[e+1],this}toArray(t=[],e=0){return t[e]=this.x,t[e+1]=this.y,t}fromBufferAttribute(t,e){return this.x=t.getX(e),this.y=t.getY(e),this}rotateAround(t,e){const n=Math.cos(e),s=Math.sin(e),r=this.x-t.x,a=this.y-t.y;return this.x=r*n-a*s+t.x,this.y=r*s+a*n+t.y,this}random(){return this.x=Math.random(),this.y=Math.random(),this}*[Symbol.iterator](){yield this.x,yield this.y}}class Ot{constructor(t,e,n,s,r,a,o,l,h){Ot.prototype.isMatrix3=!0,this.elements=[1,0,0,0,1,0,0,0,1],t!==void 0&&this.set(t,e,n,s,r,a,o,l,h)}set(t,e,n,s,r,a,o,l,h){const d=this.elements;return d[0]=t,d[1]=s,d[2]=o,d[3]=e,d[4]=r,d[5]=l,d[6]=n,d[7]=a,d[8]=h,this}identity(){return this.set(1,0,0,0,1,0,0,0,1),this}copy(t){const e=this.elements,n=t.elements;return e[0]=n[0],e[1]=n[1],e[2]=n[2],e[3]=n[3],e[4]=n[4],e[5]=n[5],e[6]=n[6],e[7]=n[7],e[8]=n[8],this}extractBasis(t,e,n){return t.setFromMatrix3Column(this,0),e.setFromMatrix3Column(this,1),n.setFromMatrix3Column(this,2),this}setFromMatrix4(t){const e=t.elements;return this.set(e[0],e[4],e[8],e[1],e[5],e[9],e[2],e[6],e[10]),this}multiply(t){return this.multiplyMatrices(this,t)}premultiply(t){return this.multiplyMatrices(t,this)}multiplyMatrices(t,e){const n=t.elements,s=e.elements,r=this.elements,a=n[0],o=n[3],l=n[6],h=n[1],d=n[4],c=n[7],u=n[2],f=n[5],g=n[8],v=s[0],m=s[3],p=s[6],y=s[1],_=s[4],S=s[7],P=s[2],T=s[5],A=s[8];return r[0]=a*v+o*y+l*P,r[3]=a*m+o*_+l*T,r[6]=a*p+o*S+l*A,r[1]=h*v+d*y+c*P,r[4]=h*m+d*_+c*T,r[7]=h*p+d*S+c*A,r[2]=u*v+f*y+g*P,r[5]=u*m+f*_+g*T,r[8]=u*p+f*S+g*A,this}multiplyScalar(t){const e=this.elements;return e[0]*=t,e[3]*=t,e[6]*=t,e[1]*=t,e[4]*=t,e[7]*=t,e[2]*=t,e[5]*=t,e[8]*=t,this}determinant(){const t=this.elements,e=t[0],n=t[1],s=t[2],r=t[3],a=t[4],o=t[5],l=t[6],h=t[7],d=t[8];return e*a*d-e*o*h-n*r*d+n*o*l+s*r*h-s*a*l}invert(){const t=this.elements,e=t[0],n=t[1],s=t[2],r=t[3],a=t[4],o=t[5],l=t[6],h=t[7],d=t[8],c=d*a-o*h,u=o*l-d*r,f=h*r-a*l,g=e*c+n*u+s*f;if(g===0)return this.set(0,0,0,0,0,0,0,0,0);const v=1/g;return t[0]=c*v,t[1]=(s*h-d*n)*v,t[2]=(o*n-s*a)*v,t[3]=u*v,t[4]=(d*e-s*l)*v,t[5]=(s*r-o*e)*v,t[6]=f*v,t[7]=(n*l-h*e)*v,t[8]=(a*e-n*r)*v,this}transpose(){let t;const e=this.elements;return t=e[1],e[1]=e[3],e[3]=t,t=e[2],e[2]=e[6],e[6]=t,t=e[5],e[5]=e[7],e[7]=t,this}getNormalMatrix(t){return this.setFromMatrix4(t).invert().transpose()}transposeIntoArray(t){const e=this.elements;return t[0]=e[0],t[1]=e[3],t[2]=e[6],t[3]=e[1],t[4]=e[4],t[5]=e[7],t[6]=e[2],t[7]=e[5],t[8]=e[8],this}setUvTransform(t,e,n,s,r,a,o){const l=Math.cos(r),h=Math.sin(r);return this.set(n*l,n*h,-n*(l*a+h*o)+a+t,-s*h,s*l,-s*(-h*a+l*o)+o+e,0,0,1),this}scale(t,e){return this.premultiply(fr.makeScale(t,e)),this}rotate(t){return this.premultiply(fr.makeRotation(-t)),this}translate(t,e){return this.premultiply(fr.makeTranslation(t,e)),this}makeTranslation(t,e){return t.isVector2?this.set(1,0,t.x,0,1,t.y,0,0,1):this.set(1,0,t,0,1,e,0,0,1),this}makeRotation(t){const e=Math.cos(t),n=Math.sin(t);return this.set(e,-n,0,n,e,0,0,0,1),this}makeScale(t,e){return this.set(t,0,0,0,e,0,0,0,1),this}equals(t){const e=this.elements,n=t.elements;for(let s=0;s<9;s++)if(e[s]!==n[s])return!1;return!0}fromArray(t,e=0){for(let n=0;n<9;n++)this.elements[n]=t[n+e];return this}toArray(t=[],e=0){const n=this.elements;return t[e]=n[0],t[e+1]=n[1],t[e+2]=n[2],t[e+3]=n[3],t[e+4]=n[4],t[e+5]=n[5],t[e+6]=n[6],t[e+7]=n[7],t[e+8]=n[8],t}clone(){return new this.constructor().fromArray(this.elements)}}const fr=new Ot;function Xl(i){for(let t=i.length-1;t>=0;--t)if(i[t]>=65535)return!0;return!1}function Js(i){return document.createElementNS("http://www.w3.org/1999/xhtml",i)}function Ch(){const i=Js("canvas");return i.style.display="block",i}const po={};function Xs(i){i in po||(po[i]=!0,console.warn(i))}function Ph(i,t,e){return new Promise(function(n,s){function r(){switch(i.clientWaitSync(t,i.SYNC_FLUSH_COMMANDS_BIT,0)){case i.WAIT_FAILED:s();break;case i.TIMEOUT_EXPIRED:setTimeout(r,e);break;default:n()}}setTimeout(r,e)})}function Lh(i){const t=i.elements;t[2]=.5*t[2]+.5*t[3],t[6]=.5*t[6]+.5*t[7],t[10]=.5*t[10]+.5*t[11],t[14]=.5*t[14]+.5*t[15]}function Dh(i){const t=i.elements;t[11]===-1?(t[10]=-t[10]-1,t[14]=-t[14]):(t[10]=-t[10],t[14]=-t[14]+1)}const mo=new Ot().set(.8224621,.177538,0,.0331941,.9668058,0,.0170827,.0723974,.9105199),go=new Ot().set(1.2249401,-.2249404,0,-.0420569,1.0420571,0,-.0196376,-.0786361,1.0982735),zi={[In]:{transfer:Ks,primaries:js,luminanceCoefficients:[.2126,.7152,.0722],toReference:i=>i,fromReference:i=>i},[je]:{transfer:se,primaries:js,luminanceCoefficients:[.2126,.7152,.0722],toReference:i=>i.convertSRGBToLinear(),fromReference:i=>i.convertLinearToSRGB()},[ir]:{transfer:Ks,primaries:Zs,luminanceCoefficients:[.2289,.6917,.0793],toReference:i=>i.applyMatrix3(go),fromReference:i=>i.applyMatrix3(mo)},[Va]:{transfer:se,primaries:Zs,luminanceCoefficients:[.2289,.6917,.0793],toReference:i=>i.convertSRGBToLinear().applyMatrix3(go),fromReference:i=>i.applyMatrix3(mo).convertLinearToSRGB()}},Ih=new Set([In,ir]),Jt={enabled:!0,_workingColorSpace:In,get workingColorSpace(){return this._workingColorSpace},set workingColorSpace(i){if(!Ih.has(i))throw new Error(`Unsupported working color space, "${i}".`);this._workingColorSpace=i},convert:function(i,t,e){if(this.enabled===!1||t===e||!t||!e)return i;const n=zi[t].toReference,s=zi[e].fromReference;return s(n(i))},fromWorkingColorSpace:function(i,t){return this.convert(i,this._workingColorSpace,t)},toWorkingColorSpace:function(i,t){return this.convert(i,t,this._workingColorSpace)},getPrimaries:function(i){return zi[i].primaries},getTransfer:function(i){return i===Cn?Ks:zi[i].transfer},getLuminanceCoefficients:function(i,t=this._workingColorSpace){return i.fromArray(zi[t].luminanceCoefficients)}};function Ti(i){return i<.04045?i*.0773993808:Math.pow(i*.9478672986+.0521327014,2.4)}function pr(i){return i<.0031308?i*12.92:1.055*Math.pow(i,.41666)-.055}let ii;class Uh{static getDataURL(t){if(/^data:/i.test(t.src)||typeof HTMLCanvasElement>"u")return t.src;let e;if(t instanceof HTMLCanvasElement)e=t;else{ii===void 0&&(ii=Js("canvas")),ii.width=t.width,ii.height=t.height;const n=ii.getContext("2d");t instanceof ImageData?n.putImageData(t,0,0):n.drawImage(t,0,0,t.width,t.height),e=ii}return e.width>2048||e.height>2048?(console.warn("THREE.ImageUtils.getDataURL: Image converted to jpg for performance reasons",t),e.toDataURL("image/jpeg",.6)):e.toDataURL("image/png")}static sRGBToLinear(t){if(typeof HTMLImageElement<"u"&&t instanceof HTMLImageElement||typeof HTMLCanvasElement<"u"&&t instanceof HTMLCanvasElement||typeof ImageBitmap<"u"&&t instanceof ImageBitmap){const e=Js("canvas");e.width=t.width,e.height=t.height;const n=e.getContext("2d");n.drawImage(t,0,0,t.width,t.height);const s=n.getImageData(0,0,t.width,t.height),r=s.data;for(let a=0;a<r.length;a++)r[a]=Ti(r[a]/255)*255;return n.putImageData(s,0,0),e}else if(t.data){const e=t.data.slice(0);for(let n=0;n<e.length;n++)e instanceof Uint8Array||e instanceof Uint8ClampedArray?e[n]=Math.floor(Ti(e[n]/255)*255):e[n]=Ti(e[n]);return{data:e,width:t.width,height:t.height}}else return console.warn("THREE.ImageUtils.sRGBToLinear(): Unsupported image type. No color space conversion applied."),t}}let Nh=0;class Yl{constructor(t=null){this.isSource=!0,Object.defineProperty(this,"id",{value:Nh++}),this.uuid=Fi(),this.data=t,this.dataReady=!0,this.version=0}set needsUpdate(t){t===!0&&this.version++}toJSON(t){const e=t===void 0||typeof t=="string";if(!e&&t.images[this.uuid]!==void 0)return t.images[this.uuid];const n={uuid:this.uuid,url:""},s=this.data;if(s!==null){let r;if(Array.isArray(s)){r=[];for(let a=0,o=s.length;a<o;a++)s[a].isDataTexture?r.push(mr(s[a].image)):r.push(mr(s[a]))}else r=mr(s);n.url=r}return e||(t.images[this.uuid]=n),n}}function mr(i){return typeof HTMLImageElement<"u"&&i instanceof HTMLImageElement||typeof HTMLCanvasElement<"u"&&i instanceof HTMLCanvasElement||typeof ImageBitmap<"u"&&i instanceof ImageBitmap?Uh.getDataURL(i):i.data?{data:Array.from(i.data),width:i.width,height:i.height,type:i.data.constructor.name}:(console.warn("THREE.Texture: Unable to serialize Texture."),{})}let Fh=0;class be extends Ni{constructor(t=be.DEFAULT_IMAGE,e=be.DEFAULT_MAPPING,n=xn,s=xn,r=We,a=jn,o=rn,l=Mn,h=be.DEFAULT_ANISOTROPY,d=Cn){super(),this.isTexture=!0,Object.defineProperty(this,"id",{value:Fh++}),this.uuid=Fi(),this.name="",this.source=new Yl(t),this.mipmaps=[],this.mapping=e,this.channel=0,this.wrapS=n,this.wrapT=s,this.magFilter=r,this.minFilter=a,this.anisotropy=h,this.format=o,this.internalFormat=null,this.type=l,this.offset=new Ht(0,0),this.repeat=new Ht(1,1),this.center=new Ht(0,0),this.rotation=0,this.matrixAutoUpdate=!0,this.matrix=new Ot,this.generateMipmaps=!0,this.premultiplyAlpha=!1,this.flipY=!0,this.unpackAlignment=4,this.colorSpace=d,this.userData={},this.version=0,this.onUpdate=null,this.isRenderTargetTexture=!1,this.pmremVersion=0}get image(){return this.source.data}set image(t=null){this.source.data=t}updateMatrix(){this.matrix.setUvTransform(this.offset.x,this.offset.y,this.repeat.x,this.repeat.y,this.rotation,this.center.x,this.center.y)}clone(){return new this.constructor().copy(this)}copy(t){return this.name=t.name,this.source=t.source,this.mipmaps=t.mipmaps.slice(0),this.mapping=t.mapping,this.channel=t.channel,this.wrapS=t.wrapS,this.wrapT=t.wrapT,this.magFilter=t.magFilter,this.minFilter=t.minFilter,this.anisotropy=t.anisotropy,this.format=t.format,this.internalFormat=t.internalFormat,this.type=t.type,this.offset.copy(t.offset),this.repeat.copy(t.repeat),this.center.copy(t.center),this.rotation=t.rotation,this.matrixAutoUpdate=t.matrixAutoUpdate,this.matrix.copy(t.matrix),this.generateMipmaps=t.generateMipmaps,this.premultiplyAlpha=t.premultiplyAlpha,this.flipY=t.flipY,this.unpackAlignment=t.unpackAlignment,this.colorSpace=t.colorSpace,this.userData=JSON.parse(JSON.stringify(t.userData)),this.needsUpdate=!0,this}toJSON(t){const e=t===void 0||typeof t=="string";if(!e&&t.textures[this.uuid]!==void 0)return t.textures[this.uuid];const n={metadata:{version:4.6,type:"Texture",generator:"Texture.toJSON"},uuid:this.uuid,name:this.name,image:this.source.toJSON(t).uuid,mapping:this.mapping,channel:this.channel,repeat:[this.repeat.x,this.repeat.y],offset:[this.offset.x,this.offset.y],center:[this.center.x,this.center.y],rotation:this.rotation,wrap:[this.wrapS,this.wrapT],format:this.format,internalFormat:this.internalFormat,type:this.type,colorSpace:this.colorSpace,minFilter:this.minFilter,magFilter:this.magFilter,anisotropy:this.anisotropy,flipY:this.flipY,generateMipmaps:this.generateMipmaps,premultiplyAlpha:this.premultiplyAlpha,unpackAlignment:this.unpackAlignment};return Object.keys(this.userData).length>0&&(n.userData=this.userData),e||(t.textures[this.uuid]=n),n}dispose(){this.dispatchEvent({type:"dispose"})}transformUv(t){if(this.mapping!==Il)return t;if(t.applyMatrix3(this.matrix),t.x<0||t.x>1)switch(this.wrapS){case ss:t.x=t.x-Math.floor(t.x);break;case xn:t.x=t.x<0?0:1;break;case sa:Math.abs(Math.floor(t.x)%2)===1?t.x=Math.ceil(t.x)-t.x:t.x=t.x-Math.floor(t.x);break}if(t.y<0||t.y>1)switch(this.wrapT){case ss:t.y=t.y-Math.floor(t.y);break;case xn:t.y=t.y<0?0:1;break;case sa:Math.abs(Math.floor(t.y)%2)===1?t.y=Math.ceil(t.y)-t.y:t.y=t.y-Math.floor(t.y);break}return this.flipY&&(t.y=1-t.y),t}set needsUpdate(t){t===!0&&(this.version++,this.source.needsUpdate=!0)}set needsPMREMUpdate(t){t===!0&&this.pmremVersion++}}be.DEFAULT_IMAGE=null;be.DEFAULT_MAPPING=Il;be.DEFAULT_ANISOTROPY=1;class te{constructor(t=0,e=0,n=0,s=1){te.prototype.isVector4=!0,this.x=t,this.y=e,this.z=n,this.w=s}get width(){return this.z}set width(t){this.z=t}get height(){return this.w}set height(t){this.w=t}set(t,e,n,s){return this.x=t,this.y=e,this.z=n,this.w=s,this}setScalar(t){return this.x=t,this.y=t,this.z=t,this.w=t,this}setX(t){return this.x=t,this}setY(t){return this.y=t,this}setZ(t){return this.z=t,this}setW(t){return this.w=t,this}setComponent(t,e){switch(t){case 0:this.x=e;break;case 1:this.y=e;break;case 2:this.z=e;break;case 3:this.w=e;break;default:throw new Error("index is out of range: "+t)}return this}getComponent(t){switch(t){case 0:return this.x;case 1:return this.y;case 2:return this.z;case 3:return this.w;default:throw new Error("index is out of range: "+t)}}clone(){return new this.constructor(this.x,this.y,this.z,this.w)}copy(t){return this.x=t.x,this.y=t.y,this.z=t.z,this.w=t.w!==void 0?t.w:1,this}add(t){return this.x+=t.x,this.y+=t.y,this.z+=t.z,this.w+=t.w,this}addScalar(t){return this.x+=t,this.y+=t,this.z+=t,this.w+=t,this}addVectors(t,e){return this.x=t.x+e.x,this.y=t.y+e.y,this.z=t.z+e.z,this.w=t.w+e.w,this}addScaledVector(t,e){return this.x+=t.x*e,this.y+=t.y*e,this.z+=t.z*e,this.w+=t.w*e,this}sub(t){return this.x-=t.x,this.y-=t.y,this.z-=t.z,this.w-=t.w,this}subScalar(t){return this.x-=t,this.y-=t,this.z-=t,this.w-=t,this}subVectors(t,e){return this.x=t.x-e.x,this.y=t.y-e.y,this.z=t.z-e.z,this.w=t.w-e.w,this}multiply(t){return this.x*=t.x,this.y*=t.y,this.z*=t.z,this.w*=t.w,this}multiplyScalar(t){return this.x*=t,this.y*=t,this.z*=t,this.w*=t,this}applyMatrix4(t){const e=this.x,n=this.y,s=this.z,r=this.w,a=t.elements;return this.x=a[0]*e+a[4]*n+a[8]*s+a[12]*r,this.y=a[1]*e+a[5]*n+a[9]*s+a[13]*r,this.z=a[2]*e+a[6]*n+a[10]*s+a[14]*r,this.w=a[3]*e+a[7]*n+a[11]*s+a[15]*r,this}divideScalar(t){return this.multiplyScalar(1/t)}setAxisAngleFromQuaternion(t){this.w=2*Math.acos(t.w);const e=Math.sqrt(1-t.w*t.w);return e<1e-4?(this.x=1,this.y=0,this.z=0):(this.x=t.x/e,this.y=t.y/e,this.z=t.z/e),this}setAxisAngleFromRotationMatrix(t){let e,n,s,r;const l=t.elements,h=l[0],d=l[4],c=l[8],u=l[1],f=l[5],g=l[9],v=l[2],m=l[6],p=l[10];if(Math.abs(d-u)<.01&&Math.abs(c-v)<.01&&Math.abs(g-m)<.01){if(Math.abs(d+u)<.1&&Math.abs(c+v)<.1&&Math.abs(g+m)<.1&&Math.abs(h+f+p-3)<.1)return this.set(1,0,0,0),this;e=Math.PI;const _=(h+1)/2,S=(f+1)/2,P=(p+1)/2,T=(d+u)/4,A=(c+v)/4,L=(g+m)/4;return _>S&&_>P?_<.01?(n=0,s=.707106781,r=.707106781):(n=Math.sqrt(_),s=T/n,r=A/n):S>P?S<.01?(n=.707106781,s=0,r=.707106781):(s=Math.sqrt(S),n=T/s,r=L/s):P<.01?(n=.707106781,s=.707106781,r=0):(r=Math.sqrt(P),n=A/r,s=L/r),this.set(n,s,r,e),this}let y=Math.sqrt((m-g)*(m-g)+(c-v)*(c-v)+(u-d)*(u-d));return Math.abs(y)<.001&&(y=1),this.x=(m-g)/y,this.y=(c-v)/y,this.z=(u-d)/y,this.w=Math.acos((h+f+p-1)/2),this}setFromMatrixPosition(t){const e=t.elements;return this.x=e[12],this.y=e[13],this.z=e[14],this.w=e[15],this}min(t){return this.x=Math.min(this.x,t.x),this.y=Math.min(this.y,t.y),this.z=Math.min(this.z,t.z),this.w=Math.min(this.w,t.w),this}max(t){return this.x=Math.max(this.x,t.x),this.y=Math.max(this.y,t.y),this.z=Math.max(this.z,t.z),this.w=Math.max(this.w,t.w),this}clamp(t,e){return this.x=Math.max(t.x,Math.min(e.x,this.x)),this.y=Math.max(t.y,Math.min(e.y,this.y)),this.z=Math.max(t.z,Math.min(e.z,this.z)),this.w=Math.max(t.w,Math.min(e.w,this.w)),this}clampScalar(t,e){return this.x=Math.max(t,Math.min(e,this.x)),this.y=Math.max(t,Math.min(e,this.y)),this.z=Math.max(t,Math.min(e,this.z)),this.w=Math.max(t,Math.min(e,this.w)),this}clampLength(t,e){const n=this.length();return this.divideScalar(n||1).multiplyScalar(Math.max(t,Math.min(e,n)))}floor(){return this.x=Math.floor(this.x),this.y=Math.floor(this.y),this.z=Math.floor(this.z),this.w=Math.floor(this.w),this}ceil(){return this.x=Math.ceil(this.x),this.y=Math.ceil(this.y),this.z=Math.ceil(this.z),this.w=Math.ceil(this.w),this}round(){return this.x=Math.round(this.x),this.y=Math.round(this.y),this.z=Math.round(this.z),this.w=Math.round(this.w),this}roundToZero(){return this.x=Math.trunc(this.x),this.y=Math.trunc(this.y),this.z=Math.trunc(this.z),this.w=Math.trunc(this.w),this}negate(){return this.x=-this.x,this.y=-this.y,this.z=-this.z,this.w=-this.w,this}dot(t){return this.x*t.x+this.y*t.y+this.z*t.z+this.w*t.w}lengthSq(){return this.x*this.x+this.y*this.y+this.z*this.z+this.w*this.w}length(){return Math.sqrt(this.x*this.x+this.y*this.y+this.z*this.z+this.w*this.w)}manhattanLength(){return Math.abs(this.x)+Math.abs(this.y)+Math.abs(this.z)+Math.abs(this.w)}normalize(){return this.divideScalar(this.length()||1)}setLength(t){return this.normalize().multiplyScalar(t)}lerp(t,e){return this.x+=(t.x-this.x)*e,this.y+=(t.y-this.y)*e,this.z+=(t.z-this.z)*e,this.w+=(t.w-this.w)*e,this}lerpVectors(t,e,n){return this.x=t.x+(e.x-t.x)*n,this.y=t.y+(e.y-t.y)*n,this.z=t.z+(e.z-t.z)*n,this.w=t.w+(e.w-t.w)*n,this}equals(t){return t.x===this.x&&t.y===this.y&&t.z===this.z&&t.w===this.w}fromArray(t,e=0){return this.x=t[e],this.y=t[e+1],this.z=t[e+2],this.w=t[e+3],this}toArray(t=[],e=0){return t[e]=this.x,t[e+1]=this.y,t[e+2]=this.z,t[e+3]=this.w,t}fromBufferAttribute(t,e){return this.x=t.getX(e),this.y=t.getY(e),this.z=t.getZ(e),this.w=t.getW(e),this}random(){return this.x=Math.random(),this.y=Math.random(),this.z=Math.random(),this.w=Math.random(),this}*[Symbol.iterator](){yield this.x,yield this.y,yield this.z,yield this.w}}class Oh extends Ni{constructor(t=1,e=1,n={}){super(),this.isRenderTarget=!0,this.width=t,this.height=e,this.depth=1,this.scissor=new te(0,0,t,e),this.scissorTest=!1,this.viewport=new te(0,0,t,e);const s={width:t,height:e,depth:1};n=Object.assign({generateMipmaps:!1,internalFormat:null,minFilter:We,depthBuffer:!0,stencilBuffer:!1,resolveDepthBuffer:!0,resolveStencilBuffer:!0,depthTexture:null,samples:0,count:1},n);const r=new be(s,n.mapping,n.wrapS,n.wrapT,n.magFilter,n.minFilter,n.format,n.type,n.anisotropy,n.colorSpace);r.flipY=!1,r.generateMipmaps=n.generateMipmaps,r.internalFormat=n.internalFormat,this.textures=[];const a=n.count;for(let o=0;o<a;o++)this.textures[o]=r.clone(),this.textures[o].isRenderTargetTexture=!0;this.depthBuffer=n.depthBuffer,this.stencilBuffer=n.stencilBuffer,this.resolveDepthBuffer=n.resolveDepthBuffer,this.resolveStencilBuffer=n.resolveStencilBuffer,this.depthTexture=n.depthTexture,this.samples=n.samples}get texture(){return this.textures[0]}set texture(t){this.textures[0]=t}setSize(t,e,n=1){if(this.width!==t||this.height!==e||this.depth!==n){this.width=t,this.height=e,this.depth=n;for(let s=0,r=this.textures.length;s<r;s++)this.textures[s].image.width=t,this.textures[s].image.height=e,this.textures[s].image.depth=n;this.dispose()}this.viewport.set(0,0,t,e),this.scissor.set(0,0,t,e)}clone(){return new this.constructor().copy(this)}copy(t){this.width=t.width,this.height=t.height,this.depth=t.depth,this.scissor.copy(t.scissor),this.scissorTest=t.scissorTest,this.viewport.copy(t.viewport),this.textures.length=0;for(let n=0,s=t.textures.length;n<s;n++)this.textures[n]=t.textures[n].clone(),this.textures[n].isRenderTargetTexture=!0;const e=Object.assign({},t.texture.image);return this.texture.source=new Yl(e),this.depthBuffer=t.depthBuffer,this.stencilBuffer=t.stencilBuffer,this.resolveDepthBuffer=t.resolveDepthBuffer,this.resolveStencilBuffer=t.resolveStencilBuffer,t.depthTexture!==null&&(this.depthTexture=t.depthTexture.clone()),this.samples=t.samples,this}dispose(){this.dispatchEvent({type:"dispose"})}}class $n extends Oh{constructor(t=1,e=1,n={}){super(t,e,n),this.isWebGLRenderTarget=!0}}class ql extends be{constructor(t=null,e=1,n=1,s=1){super(null),this.isDataArrayTexture=!0,this.image={data:t,width:e,height:n,depth:s},this.magFilter=Ue,this.minFilter=Ue,this.wrapR=xn,this.generateMipmaps=!1,this.flipY=!1,this.unpackAlignment=1,this.layerUpdates=new Set}addLayerUpdate(t){this.layerUpdates.add(t)}clearLayerUpdates(){this.layerUpdates.clear()}}class Bh extends be{constructor(t=null,e=1,n=1,s=1){super(null),this.isData3DTexture=!0,this.image={data:t,width:e,height:n,depth:s},this.magFilter=Ue,this.minFilter=Ue,this.wrapR=xn,this.generateMipmaps=!1,this.flipY=!1,this.unpackAlignment=1}}class ls{constructor(t=0,e=0,n=0,s=1){this.isQuaternion=!0,this._x=t,this._y=e,this._z=n,this._w=s}static slerpFlat(t,e,n,s,r,a,o){let l=n[s+0],h=n[s+1],d=n[s+2],c=n[s+3];const u=r[a+0],f=r[a+1],g=r[a+2],v=r[a+3];if(o===0){t[e+0]=l,t[e+1]=h,t[e+2]=d,t[e+3]=c;return}if(o===1){t[e+0]=u,t[e+1]=f,t[e+2]=g,t[e+3]=v;return}if(c!==v||l!==u||h!==f||d!==g){let m=1-o;const p=l*u+h*f+d*g+c*v,y=p>=0?1:-1,_=1-p*p;if(_>Number.EPSILON){const P=Math.sqrt(_),T=Math.atan2(P,p*y);m=Math.sin(m*T)/P,o=Math.sin(o*T)/P}const S=o*y;if(l=l*m+u*S,h=h*m+f*S,d=d*m+g*S,c=c*m+v*S,m===1-o){const P=1/Math.sqrt(l*l+h*h+d*d+c*c);l*=P,h*=P,d*=P,c*=P}}t[e]=l,t[e+1]=h,t[e+2]=d,t[e+3]=c}static multiplyQuaternionsFlat(t,e,n,s,r,a){const o=n[s],l=n[s+1],h=n[s+2],d=n[s+3],c=r[a],u=r[a+1],f=r[a+2],g=r[a+3];return t[e]=o*g+d*c+l*f-h*u,t[e+1]=l*g+d*u+h*c-o*f,t[e+2]=h*g+d*f+o*u-l*c,t[e+3]=d*g-o*c-l*u-h*f,t}get x(){return this._x}set x(t){this._x=t,this._onChangeCallback()}get y(){return this._y}set y(t){this._y=t,this._onChangeCallback()}get z(){return this._z}set z(t){this._z=t,this._onChangeCallback()}get w(){return this._w}set w(t){this._w=t,this._onChangeCallback()}set(t,e,n,s){return this._x=t,this._y=e,this._z=n,this._w=s,this._onChangeCallback(),this}clone(){return new this.constructor(this._x,this._y,this._z,this._w)}copy(t){return this._x=t.x,this._y=t.y,this._z=t.z,this._w=t.w,this._onChangeCallback(),this}setFromEuler(t,e=!0){const n=t._x,s=t._y,r=t._z,a=t._order,o=Math.cos,l=Math.sin,h=o(n/2),d=o(s/2),c=o(r/2),u=l(n/2),f=l(s/2),g=l(r/2);switch(a){case"XYZ":this._x=u*d*c+h*f*g,this._y=h*f*c-u*d*g,this._z=h*d*g+u*f*c,this._w=h*d*c-u*f*g;break;case"YXZ":this._x=u*d*c+h*f*g,this._y=h*f*c-u*d*g,this._z=h*d*g-u*f*c,this._w=h*d*c+u*f*g;break;case"ZXY":this._x=u*d*c-h*f*g,this._y=h*f*c+u*d*g,this._z=h*d*g+u*f*c,this._w=h*d*c-u*f*g;break;case"ZYX":this._x=u*d*c-h*f*g,this._y=h*f*c+u*d*g,this._z=h*d*g-u*f*c,this._w=h*d*c+u*f*g;break;case"YZX":this._x=u*d*c+h*f*g,this._y=h*f*c+u*d*g,this._z=h*d*g-u*f*c,this._w=h*d*c-u*f*g;break;case"XZY":this._x=u*d*c-h*f*g,this._y=h*f*c-u*d*g,this._z=h*d*g+u*f*c,this._w=h*d*c+u*f*g;break;default:console.warn("THREE.Quaternion: .setFromEuler() encountered an unknown order: "+a)}return e===!0&&this._onChangeCallback(),this}setFromAxisAngle(t,e){const n=e/2,s=Math.sin(n);return this._x=t.x*s,this._y=t.y*s,this._z=t.z*s,this._w=Math.cos(n),this._onChangeCallback(),this}setFromRotationMatrix(t){const e=t.elements,n=e[0],s=e[4],r=e[8],a=e[1],o=e[5],l=e[9],h=e[2],d=e[6],c=e[10],u=n+o+c;if(u>0){const f=.5/Math.sqrt(u+1);this._w=.25/f,this._x=(d-l)*f,this._y=(r-h)*f,this._z=(a-s)*f}else if(n>o&&n>c){const f=2*Math.sqrt(1+n-o-c);this._w=(d-l)/f,this._x=.25*f,this._y=(s+a)/f,this._z=(r+h)/f}else if(o>c){const f=2*Math.sqrt(1+o-n-c);this._w=(r-h)/f,this._x=(s+a)/f,this._y=.25*f,this._z=(l+d)/f}else{const f=2*Math.sqrt(1+c-n-o);this._w=(a-s)/f,this._x=(r+h)/f,this._y=(l+d)/f,this._z=.25*f}return this._onChangeCallback(),this}setFromUnitVectors(t,e){let n=t.dot(e)+1;return n<Number.EPSILON?(n=0,Math.abs(t.x)>Math.abs(t.z)?(this._x=-t.y,this._y=t.x,this._z=0,this._w=n):(this._x=0,this._y=-t.z,this._z=t.y,this._w=n)):(this._x=t.y*e.z-t.z*e.y,this._y=t.z*e.x-t.x*e.z,this._z=t.x*e.y-t.y*e.x,this._w=n),this.normalize()}angleTo(t){return 2*Math.acos(Math.abs(Ee(this.dot(t),-1,1)))}rotateTowards(t,e){const n=this.angleTo(t);if(n===0)return this;const s=Math.min(1,e/n);return this.slerp(t,s),this}identity(){return this.set(0,0,0,1)}invert(){return this.conjugate()}conjugate(){return this._x*=-1,this._y*=-1,this._z*=-1,this._onChangeCallback(),this}dot(t){return this._x*t._x+this._y*t._y+this._z*t._z+this._w*t._w}lengthSq(){return this._x*this._x+this._y*this._y+this._z*this._z+this._w*this._w}length(){return Math.sqrt(this._x*this._x+this._y*this._y+this._z*this._z+this._w*this._w)}normalize(){let t=this.length();return t===0?(this._x=0,this._y=0,this._z=0,this._w=1):(t=1/t,this._x=this._x*t,this._y=this._y*t,this._z=this._z*t,this._w=this._w*t),this._onChangeCallback(),this}multiply(t){return this.multiplyQuaternions(this,t)}premultiply(t){return this.multiplyQuaternions(t,this)}multiplyQuaternions(t,e){const n=t._x,s=t._y,r=t._z,a=t._w,o=e._x,l=e._y,h=e._z,d=e._w;return this._x=n*d+a*o+s*h-r*l,this._y=s*d+a*l+r*o-n*h,this._z=r*d+a*h+n*l-s*o,this._w=a*d-n*o-s*l-r*h,this._onChangeCallback(),this}slerp(t,e){if(e===0)return this;if(e===1)return this.copy(t);const n=this._x,s=this._y,r=this._z,a=this._w;let o=a*t._w+n*t._x+s*t._y+r*t._z;if(o<0?(this._w=-t._w,this._x=-t._x,this._y=-t._y,this._z=-t._z,o=-o):this.copy(t),o>=1)return this._w=a,this._x=n,this._y=s,this._z=r,this;const l=1-o*o;if(l<=Number.EPSILON){const f=1-e;return this._w=f*a+e*this._w,this._x=f*n+e*this._x,this._y=f*s+e*this._y,this._z=f*r+e*this._z,this.normalize(),this}const h=Math.sqrt(l),d=Math.atan2(h,o),c=Math.sin((1-e)*d)/h,u=Math.sin(e*d)/h;return this._w=a*c+this._w*u,this._x=n*c+this._x*u,this._y=s*c+this._y*u,this._z=r*c+this._z*u,this._onChangeCallback(),this}slerpQuaternions(t,e,n){return this.copy(t).slerp(e,n)}random(){const t=2*Math.PI*Math.random(),e=2*Math.PI*Math.random(),n=Math.random(),s=Math.sqrt(1-n),r=Math.sqrt(n);return this.set(s*Math.sin(t),s*Math.cos(t),r*Math.sin(e),r*Math.cos(e))}equals(t){return t._x===this._x&&t._y===this._y&&t._z===this._z&&t._w===this._w}fromArray(t,e=0){return this._x=t[e],this._y=t[e+1],this._z=t[e+2],this._w=t[e+3],this._onChangeCallback(),this}toArray(t=[],e=0){return t[e]=this._x,t[e+1]=this._y,t[e+2]=this._z,t[e+3]=this._w,t}fromBufferAttribute(t,e){return this._x=t.getX(e),this._y=t.getY(e),this._z=t.getZ(e),this._w=t.getW(e),this._onChangeCallback(),this}toJSON(){return this.toArray()}_onChange(t){return this._onChangeCallback=t,this}_onChangeCallback(){}*[Symbol.iterator](){yield this._x,yield this._y,yield this._z,yield this._w}}class R{constructor(t=0,e=0,n=0){R.prototype.isVector3=!0,this.x=t,this.y=e,this.z=n}set(t,e,n){return n===void 0&&(n=this.z),this.x=t,this.y=e,this.z=n,this}setScalar(t){return this.x=t,this.y=t,this.z=t,this}setX(t){return this.x=t,this}setY(t){return this.y=t,this}setZ(t){return this.z=t,this}setComponent(t,e){switch(t){case 0:this.x=e;break;case 1:this.y=e;break;case 2:this.z=e;break;default:throw new Error("index is out of range: "+t)}return this}getComponent(t){switch(t){case 0:return this.x;case 1:return this.y;case 2:return this.z;default:throw new Error("index is out of range: "+t)}}clone(){return new this.constructor(this.x,this.y,this.z)}copy(t){return this.x=t.x,this.y=t.y,this.z=t.z,this}add(t){return this.x+=t.x,this.y+=t.y,this.z+=t.z,this}addScalar(t){return this.x+=t,this.y+=t,this.z+=t,this}addVectors(t,e){return this.x=t.x+e.x,this.y=t.y+e.y,this.z=t.z+e.z,this}addScaledVector(t,e){return this.x+=t.x*e,this.y+=t.y*e,this.z+=t.z*e,this}sub(t){return this.x-=t.x,this.y-=t.y,this.z-=t.z,this}subScalar(t){return this.x-=t,this.y-=t,this.z-=t,this}subVectors(t,e){return this.x=t.x-e.x,this.y=t.y-e.y,this.z=t.z-e.z,this}multiply(t){return this.x*=t.x,this.y*=t.y,this.z*=t.z,this}multiplyScalar(t){return this.x*=t,this.y*=t,this.z*=t,this}multiplyVectors(t,e){return this.x=t.x*e.x,this.y=t.y*e.y,this.z=t.z*e.z,this}applyEuler(t){return this.applyQuaternion(_o.setFromEuler(t))}applyAxisAngle(t,e){return this.applyQuaternion(_o.setFromAxisAngle(t,e))}applyMatrix3(t){const e=this.x,n=this.y,s=this.z,r=t.elements;return this.x=r[0]*e+r[3]*n+r[6]*s,this.y=r[1]*e+r[4]*n+r[7]*s,this.z=r[2]*e+r[5]*n+r[8]*s,this}applyNormalMatrix(t){return this.applyMatrix3(t).normalize()}applyMatrix4(t){const e=this.x,n=this.y,s=this.z,r=t.elements,a=1/(r[3]*e+r[7]*n+r[11]*s+r[15]);return this.x=(r[0]*e+r[4]*n+r[8]*s+r[12])*a,this.y=(r[1]*e+r[5]*n+r[9]*s+r[13])*a,this.z=(r[2]*e+r[6]*n+r[10]*s+r[14])*a,this}applyQuaternion(t){const e=this.x,n=this.y,s=this.z,r=t.x,a=t.y,o=t.z,l=t.w,h=2*(a*s-o*n),d=2*(o*e-r*s),c=2*(r*n-a*e);return this.x=e+l*h+a*c-o*d,this.y=n+l*d+o*h-r*c,this.z=s+l*c+r*d-a*h,this}project(t){return this.applyMatrix4(t.matrixWorldInverse).applyMatrix4(t.projectionMatrix)}unproject(t){return this.applyMatrix4(t.projectionMatrixInverse).applyMatrix4(t.matrixWorld)}transformDirection(t){const e=this.x,n=this.y,s=this.z,r=t.elements;return this.x=r[0]*e+r[4]*n+r[8]*s,this.y=r[1]*e+r[5]*n+r[9]*s,this.z=r[2]*e+r[6]*n+r[10]*s,this.normalize()}divide(t){return this.x/=t.x,this.y/=t.y,this.z/=t.z,this}divideScalar(t){return this.multiplyScalar(1/t)}min(t){return this.x=Math.min(this.x,t.x),this.y=Math.min(this.y,t.y),this.z=Math.min(this.z,t.z),this}max(t){return this.x=Math.max(this.x,t.x),this.y=Math.max(this.y,t.y),this.z=Math.max(this.z,t.z),this}clamp(t,e){return this.x=Math.max(t.x,Math.min(e.x,this.x)),this.y=Math.max(t.y,Math.min(e.y,this.y)),this.z=Math.max(t.z,Math.min(e.z,this.z)),this}clampScalar(t,e){return this.x=Math.max(t,Math.min(e,this.x)),this.y=Math.max(t,Math.min(e,this.y)),this.z=Math.max(t,Math.min(e,this.z)),this}clampLength(t,e){const n=this.length();return this.divideScalar(n||1).multiplyScalar(Math.max(t,Math.min(e,n)))}floor(){return this.x=Math.floor(this.x),this.y=Math.floor(this.y),this.z=Math.floor(this.z),this}ceil(){return this.x=Math.ceil(this.x),this.y=Math.ceil(this.y),this.z=Math.ceil(this.z),this}round(){return this.x=Math.round(this.x),this.y=Math.round(this.y),this.z=Math.round(this.z),this}roundToZero(){return this.x=Math.trunc(this.x),this.y=Math.trunc(this.y),this.z=Math.trunc(this.z),this}negate(){return this.x=-this.x,this.y=-this.y,this.z=-this.z,this}dot(t){return this.x*t.x+this.y*t.y+this.z*t.z}lengthSq(){return this.x*this.x+this.y*this.y+this.z*this.z}length(){return Math.sqrt(this.x*this.x+this.y*this.y+this.z*this.z)}manhattanLength(){return Math.abs(this.x)+Math.abs(this.y)+Math.abs(this.z)}normalize(){return this.divideScalar(this.length()||1)}setLength(t){return this.normalize().multiplyScalar(t)}lerp(t,e){return this.x+=(t.x-this.x)*e,this.y+=(t.y-this.y)*e,this.z+=(t.z-this.z)*e,this}lerpVectors(t,e,n){return this.x=t.x+(e.x-t.x)*n,this.y=t.y+(e.y-t.y)*n,this.z=t.z+(e.z-t.z)*n,this}cross(t){return this.crossVectors(this,t)}crossVectors(t,e){const n=t.x,s=t.y,r=t.z,a=e.x,o=e.y,l=e.z;return this.x=s*l-r*o,this.y=r*a-n*l,this.z=n*o-s*a,this}projectOnVector(t){const e=t.lengthSq();if(e===0)return this.set(0,0,0);const n=t.dot(this)/e;return this.copy(t).multiplyScalar(n)}projectOnPlane(t){return gr.copy(this).projectOnVector(t),this.sub(gr)}reflect(t){return this.sub(gr.copy(t).multiplyScalar(2*this.dot(t)))}angleTo(t){const e=Math.sqrt(this.lengthSq()*t.lengthSq());if(e===0)return Math.PI/2;const n=this.dot(t)/e;return Math.acos(Ee(n,-1,1))}distanceTo(t){return Math.sqrt(this.distanceToSquared(t))}distanceToSquared(t){const e=this.x-t.x,n=this.y-t.y,s=this.z-t.z;return e*e+n*n+s*s}manhattanDistanceTo(t){return Math.abs(this.x-t.x)+Math.abs(this.y-t.y)+Math.abs(this.z-t.z)}setFromSpherical(t){return this.setFromSphericalCoords(t.radius,t.phi,t.theta)}setFromSphericalCoords(t,e,n){const s=Math.sin(e)*t;return this.x=s*Math.sin(n),this.y=Math.cos(e)*t,this.z=s*Math.cos(n),this}setFromCylindrical(t){return this.setFromCylindricalCoords(t.radius,t.theta,t.y)}setFromCylindricalCoords(t,e,n){return this.x=t*Math.sin(e),this.y=n,this.z=t*Math.cos(e),this}setFromMatrixPosition(t){const e=t.elements;return this.x=e[12],this.y=e[13],this.z=e[14],this}setFromMatrixScale(t){const e=this.setFromMatrixColumn(t,0).length(),n=this.setFromMatrixColumn(t,1).length(),s=this.setFromMatrixColumn(t,2).length();return this.x=e,this.y=n,this.z=s,this}setFromMatrixColumn(t,e){return this.fromArray(t.elements,e*4)}setFromMatrix3Column(t,e){return this.fromArray(t.elements,e*3)}setFromEuler(t){return this.x=t._x,this.y=t._y,this.z=t._z,this}setFromColor(t){return this.x=t.r,this.y=t.g,this.z=t.b,this}equals(t){return t.x===this.x&&t.y===this.y&&t.z===this.z}fromArray(t,e=0){return this.x=t[e],this.y=t[e+1],this.z=t[e+2],this}toArray(t=[],e=0){return t[e]=this.x,t[e+1]=this.y,t[e+2]=this.z,t}fromBufferAttribute(t,e){return this.x=t.getX(e),this.y=t.getY(e),this.z=t.getZ(e),this}random(){return this.x=Math.random(),this.y=Math.random(),this.z=Math.random(),this}randomDirection(){const t=Math.random()*Math.PI*2,e=Math.random()*2-1,n=Math.sqrt(1-e*e);return this.x=n*Math.cos(t),this.y=e,this.z=n*Math.sin(t),this}*[Symbol.iterator](){yield this.x,yield this.y,yield this.z}}const gr=new R,_o=new ls;class Un{constructor(t=new R(1/0,1/0,1/0),e=new R(-1/0,-1/0,-1/0)){this.isBox3=!0,this.min=t,this.max=e}set(t,e){return this.min.copy(t),this.max.copy(e),this}setFromArray(t){this.makeEmpty();for(let e=0,n=t.length;e<n;e+=3)this.expandByPoint(Je.fromArray(t,e));return this}setFromBufferAttribute(t){this.makeEmpty();for(let e=0,n=t.count;e<n;e++)this.expandByPoint(Je.fromBufferAttribute(t,e));return this}setFromPoints(t){this.makeEmpty();for(let e=0,n=t.length;e<n;e++)this.expandByPoint(t[e]);return this}setFromCenterAndSize(t,e){const n=Je.copy(e).multiplyScalar(.5);return this.min.copy(t).sub(n),this.max.copy(t).add(n),this}setFromObject(t,e=!1){return this.makeEmpty(),this.expandByObject(t,e)}clone(){return new this.constructor().copy(this)}copy(t){return this.min.copy(t.min),this.max.copy(t.max),this}makeEmpty(){return this.min.x=this.min.y=this.min.z=1/0,this.max.x=this.max.y=this.max.z=-1/0,this}isEmpty(){return this.max.x<this.min.x||this.max.y<this.min.y||this.max.z<this.min.z}getCenter(t){return this.isEmpty()?t.set(0,0,0):t.addVectors(this.min,this.max).multiplyScalar(.5)}getSize(t){return this.isEmpty()?t.set(0,0,0):t.subVectors(this.max,this.min)}expandByPoint(t){return this.min.min(t),this.max.max(t),this}expandByVector(t){return this.min.sub(t),this.max.add(t),this}expandByScalar(t){return this.min.addScalar(-t),this.max.addScalar(t),this}expandByObject(t,e=!1){t.updateWorldMatrix(!1,!1);const n=t.geometry;if(n!==void 0){const r=n.getAttribute("position");if(e===!0&&r!==void 0&&t.isInstancedMesh!==!0)for(let a=0,o=r.count;a<o;a++)t.isMesh===!0?t.getVertexPosition(a,Je):Je.fromBufferAttribute(r,a),Je.applyMatrix4(t.matrixWorld),this.expandByPoint(Je);else t.boundingBox!==void 0?(t.boundingBox===null&&t.computeBoundingBox(),fs.copy(t.boundingBox)):(n.boundingBox===null&&n.computeBoundingBox(),fs.copy(n.boundingBox)),fs.applyMatrix4(t.matrixWorld),this.union(fs)}const s=t.children;for(let r=0,a=s.length;r<a;r++)this.expandByObject(s[r],e);return this}containsPoint(t){return t.x>=this.min.x&&t.x<=this.max.x&&t.y>=this.min.y&&t.y<=this.max.y&&t.z>=this.min.z&&t.z<=this.max.z}containsBox(t){return this.min.x<=t.min.x&&t.max.x<=this.max.x&&this.min.y<=t.min.y&&t.max.y<=this.max.y&&this.min.z<=t.min.z&&t.max.z<=this.max.z}getParameter(t,e){return e.set((t.x-this.min.x)/(this.max.x-this.min.x),(t.y-this.min.y)/(this.max.y-this.min.y),(t.z-this.min.z)/(this.max.z-this.min.z))}intersectsBox(t){return t.max.x>=this.min.x&&t.min.x<=this.max.x&&t.max.y>=this.min.y&&t.min.y<=this.max.y&&t.max.z>=this.min.z&&t.min.z<=this.max.z}intersectsSphere(t){return this.clampPoint(t.center,Je),Je.distanceToSquared(t.center)<=t.radius*t.radius}intersectsPlane(t){let e,n;return t.normal.x>0?(e=t.normal.x*this.min.x,n=t.normal.x*this.max.x):(e=t.normal.x*this.max.x,n=t.normal.x*this.min.x),t.normal.y>0?(e+=t.normal.y*this.min.y,n+=t.normal.y*this.max.y):(e+=t.normal.y*this.max.y,n+=t.normal.y*this.min.y),t.normal.z>0?(e+=t.normal.z*this.min.z,n+=t.normal.z*this.max.z):(e+=t.normal.z*this.max.z,n+=t.normal.z*this.min.z),e<=-t.constant&&n>=-t.constant}intersectsTriangle(t){if(this.isEmpty())return!1;this.getCenter(Hi),ps.subVectors(this.max,Hi),si.subVectors(t.a,Hi),ri.subVectors(t.b,Hi),ai.subVectors(t.c,Hi),Sn.subVectors(ri,si),wn.subVectors(ai,ri),Fn.subVectors(si,ai);let e=[0,-Sn.z,Sn.y,0,-wn.z,wn.y,0,-Fn.z,Fn.y,Sn.z,0,-Sn.x,wn.z,0,-wn.x,Fn.z,0,-Fn.x,-Sn.y,Sn.x,0,-wn.y,wn.x,0,-Fn.y,Fn.x,0];return!_r(e,si,ri,ai,ps)||(e=[1,0,0,0,1,0,0,0,1],!_r(e,si,ri,ai,ps))?!1:(ms.crossVectors(Sn,wn),e=[ms.x,ms.y,ms.z],_r(e,si,ri,ai,ps))}clampPoint(t,e){return e.copy(t).clamp(this.min,this.max)}distanceToPoint(t){return this.clampPoint(t,Je).distanceTo(t)}getBoundingSphere(t){return this.isEmpty()?t.makeEmpty():(this.getCenter(t.center),t.radius=this.getSize(Je).length()*.5),t}intersect(t){return this.min.max(t.min),this.max.min(t.max),this.isEmpty()&&this.makeEmpty(),this}union(t){return this.min.min(t.min),this.max.max(t.max),this}applyMatrix4(t){return this.isEmpty()?this:(dn[0].set(this.min.x,this.min.y,this.min.z).applyMatrix4(t),dn[1].set(this.min.x,this.min.y,this.max.z).applyMatrix4(t),dn[2].set(this.min.x,this.max.y,this.min.z).applyMatrix4(t),dn[3].set(this.min.x,this.max.y,this.max.z).applyMatrix4(t),dn[4].set(this.max.x,this.min.y,this.min.z).applyMatrix4(t),dn[5].set(this.max.x,this.min.y,this.max.z).applyMatrix4(t),dn[6].set(this.max.x,this.max.y,this.min.z).applyMatrix4(t),dn[7].set(this.max.x,this.max.y,this.max.z).applyMatrix4(t),this.setFromPoints(dn),this)}translate(t){return this.min.add(t),this.max.add(t),this}equals(t){return t.min.equals(this.min)&&t.max.equals(this.max)}}const dn=[new R,new R,new R,new R,new R,new R,new R,new R],Je=new R,fs=new Un,si=new R,ri=new R,ai=new R,Sn=new R,wn=new R,Fn=new R,Hi=new R,ps=new R,ms=new R,On=new R;function _r(i,t,e,n,s){for(let r=0,a=i.length-3;r<=a;r+=3){On.fromArray(i,r);const o=s.x*Math.abs(On.x)+s.y*Math.abs(On.y)+s.z*Math.abs(On.z),l=t.dot(On),h=e.dot(On),d=n.dot(On);if(Math.max(-Math.max(l,h,d),Math.min(l,h,d))>o)return!1}return!0}const kh=new Un,Gi=new R,xr=new R;class Oi{constructor(t=new R,e=-1){this.isSphere=!0,this.center=t,this.radius=e}set(t,e){return this.center.copy(t),this.radius=e,this}setFromPoints(t,e){const n=this.center;e!==void 0?n.copy(e):kh.setFromPoints(t).getCenter(n);let s=0;for(let r=0,a=t.length;r<a;r++)s=Math.max(s,n.distanceToSquared(t[r]));return this.radius=Math.sqrt(s),this}copy(t){return this.center.copy(t.center),this.radius=t.radius,this}isEmpty(){return this.radius<0}makeEmpty(){return this.center.set(0,0,0),this.radius=-1,this}containsPoint(t){return t.distanceToSquared(this.center)<=this.radius*this.radius}distanceToPoint(t){return t.distanceTo(this.center)-this.radius}intersectsSphere(t){const e=this.radius+t.radius;return t.center.distanceToSquared(this.center)<=e*e}intersectsBox(t){return t.intersectsSphere(this)}intersectsPlane(t){return Math.abs(t.distanceToPoint(this.center))<=this.radius}clampPoint(t,e){const n=this.center.distanceToSquared(t);return e.copy(t),n>this.radius*this.radius&&(e.sub(this.center).normalize(),e.multiplyScalar(this.radius).add(this.center)),e}getBoundingBox(t){return this.isEmpty()?(t.makeEmpty(),t):(t.set(this.center,this.center),t.expandByScalar(this.radius),t)}applyMatrix4(t){return this.center.applyMatrix4(t),this.radius=this.radius*t.getMaxScaleOnAxis(),this}translate(t){return this.center.add(t),this}expandByPoint(t){if(this.isEmpty())return this.center.copy(t),this.radius=0,this;Gi.subVectors(t,this.center);const e=Gi.lengthSq();if(e>this.radius*this.radius){const n=Math.sqrt(e),s=(n-this.radius)*.5;this.center.addScaledVector(Gi,s/n),this.radius+=s}return this}union(t){return t.isEmpty()?this:this.isEmpty()?(this.copy(t),this):(this.center.equals(t.center)===!0?this.radius=Math.max(this.radius,t.radius):(xr.subVectors(t.center,this.center).setLength(t.radius),this.expandByPoint(Gi.copy(t.center).add(xr)),this.expandByPoint(Gi.copy(t.center).sub(xr))),this)}equals(t){return t.center.equals(this.center)&&t.radius===this.radius}clone(){return new this.constructor().copy(this)}}const fn=new R,vr=new R,gs=new R,En=new R,Mr=new R,_s=new R,yr=new R;class Xa{constructor(t=new R,e=new R(0,0,-1)){this.origin=t,this.direction=e}set(t,e){return this.origin.copy(t),this.direction.copy(e),this}copy(t){return this.origin.copy(t.origin),this.direction.copy(t.direction),this}at(t,e){return e.copy(this.origin).addScaledVector(this.direction,t)}lookAt(t){return this.direction.copy(t).sub(this.origin).normalize(),this}recast(t){return this.origin.copy(this.at(t,fn)),this}closestPointToPoint(t,e){e.subVectors(t,this.origin);const n=e.dot(this.direction);return n<0?e.copy(this.origin):e.copy(this.origin).addScaledVector(this.direction,n)}distanceToPoint(t){return Math.sqrt(this.distanceSqToPoint(t))}distanceSqToPoint(t){const e=fn.subVectors(t,this.origin).dot(this.direction);return e<0?this.origin.distanceToSquared(t):(fn.copy(this.origin).addScaledVector(this.direction,e),fn.distanceToSquared(t))}distanceSqToSegment(t,e,n,s){vr.copy(t).add(e).multiplyScalar(.5),gs.copy(e).sub(t).normalize(),En.copy(this.origin).sub(vr);const r=t.distanceTo(e)*.5,a=-this.direction.dot(gs),o=En.dot(this.direction),l=-En.dot(gs),h=En.lengthSq(),d=Math.abs(1-a*a);let c,u,f,g;if(d>0)if(c=a*l-o,u=a*o-l,g=r*d,c>=0)if(u>=-g)if(u<=g){const v=1/d;c*=v,u*=v,f=c*(c+a*u+2*o)+u*(a*c+u+2*l)+h}else u=r,c=Math.max(0,-(a*u+o)),f=-c*c+u*(u+2*l)+h;else u=-r,c=Math.max(0,-(a*u+o)),f=-c*c+u*(u+2*l)+h;else u<=-g?(c=Math.max(0,-(-a*r+o)),u=c>0?-r:Math.min(Math.max(-r,-l),r),f=-c*c+u*(u+2*l)+h):u<=g?(c=0,u=Math.min(Math.max(-r,-l),r),f=u*(u+2*l)+h):(c=Math.max(0,-(a*r+o)),u=c>0?r:Math.min(Math.max(-r,-l),r),f=-c*c+u*(u+2*l)+h);else u=a>0?-r:r,c=Math.max(0,-(a*u+o)),f=-c*c+u*(u+2*l)+h;return n&&n.copy(this.origin).addScaledVector(this.direction,c),s&&s.copy(vr).addScaledVector(gs,u),f}intersectSphere(t,e){fn.subVectors(t.center,this.origin);const n=fn.dot(this.direction),s=fn.dot(fn)-n*n,r=t.radius*t.radius;if(s>r)return null;const a=Math.sqrt(r-s),o=n-a,l=n+a;return l<0?null:o<0?this.at(l,e):this.at(o,e)}intersectsSphere(t){return this.distanceSqToPoint(t.center)<=t.radius*t.radius}distanceToPlane(t){const e=t.normal.dot(this.direction);if(e===0)return t.distanceToPoint(this.origin)===0?0:null;const n=-(this.origin.dot(t.normal)+t.constant)/e;return n>=0?n:null}intersectPlane(t,e){const n=this.distanceToPlane(t);return n===null?null:this.at(n,e)}intersectsPlane(t){const e=t.distanceToPoint(this.origin);return e===0||t.normal.dot(this.direction)*e<0}intersectBox(t,e){let n,s,r,a,o,l;const h=1/this.direction.x,d=1/this.direction.y,c=1/this.direction.z,u=this.origin;return h>=0?(n=(t.min.x-u.x)*h,s=(t.max.x-u.x)*h):(n=(t.max.x-u.x)*h,s=(t.min.x-u.x)*h),d>=0?(r=(t.min.y-u.y)*d,a=(t.max.y-u.y)*d):(r=(t.max.y-u.y)*d,a=(t.min.y-u.y)*d),n>a||r>s||((r>n||isNaN(n))&&(n=r),(a<s||isNaN(s))&&(s=a),c>=0?(o=(t.min.z-u.z)*c,l=(t.max.z-u.z)*c):(o=(t.max.z-u.z)*c,l=(t.min.z-u.z)*c),n>l||o>s)||((o>n||n!==n)&&(n=o),(l<s||s!==s)&&(s=l),s<0)?null:this.at(n>=0?n:s,e)}intersectsBox(t){return this.intersectBox(t,fn)!==null}intersectTriangle(t,e,n,s,r){Mr.subVectors(e,t),_s.subVectors(n,t),yr.crossVectors(Mr,_s);let a=this.direction.dot(yr),o;if(a>0){if(s)return null;o=1}else if(a<0)o=-1,a=-a;else return null;En.subVectors(this.origin,t);const l=o*this.direction.dot(_s.crossVectors(En,_s));if(l<0)return null;const h=o*this.direction.dot(Mr.cross(En));if(h<0||l+h>a)return null;const d=-o*En.dot(yr);return d<0?null:this.at(d/a,r)}applyMatrix4(t){return this.origin.applyMatrix4(t),this.direction.transformDirection(t),this}equals(t){return t.origin.equals(this.origin)&&t.direction.equals(this.direction)}clone(){return new this.constructor().copy(this)}}class ee{constructor(t,e,n,s,r,a,o,l,h,d,c,u,f,g,v,m){ee.prototype.isMatrix4=!0,this.elements=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1],t!==void 0&&this.set(t,e,n,s,r,a,o,l,h,d,c,u,f,g,v,m)}set(t,e,n,s,r,a,o,l,h,d,c,u,f,g,v,m){const p=this.elements;return p[0]=t,p[4]=e,p[8]=n,p[12]=s,p[1]=r,p[5]=a,p[9]=o,p[13]=l,p[2]=h,p[6]=d,p[10]=c,p[14]=u,p[3]=f,p[7]=g,p[11]=v,p[15]=m,this}identity(){return this.set(1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1),this}clone(){return new ee().fromArray(this.elements)}copy(t){const e=this.elements,n=t.elements;return e[0]=n[0],e[1]=n[1],e[2]=n[2],e[3]=n[3],e[4]=n[4],e[5]=n[5],e[6]=n[6],e[7]=n[7],e[8]=n[8],e[9]=n[9],e[10]=n[10],e[11]=n[11],e[12]=n[12],e[13]=n[13],e[14]=n[14],e[15]=n[15],this}copyPosition(t){const e=this.elements,n=t.elements;return e[12]=n[12],e[13]=n[13],e[14]=n[14],this}setFromMatrix3(t){const e=t.elements;return this.set(e[0],e[3],e[6],0,e[1],e[4],e[7],0,e[2],e[5],e[8],0,0,0,0,1),this}extractBasis(t,e,n){return t.setFromMatrixColumn(this,0),e.setFromMatrixColumn(this,1),n.setFromMatrixColumn(this,2),this}makeBasis(t,e,n){return this.set(t.x,e.x,n.x,0,t.y,e.y,n.y,0,t.z,e.z,n.z,0,0,0,0,1),this}extractRotation(t){const e=this.elements,n=t.elements,s=1/oi.setFromMatrixColumn(t,0).length(),r=1/oi.setFromMatrixColumn(t,1).length(),a=1/oi.setFromMatrixColumn(t,2).length();return e[0]=n[0]*s,e[1]=n[1]*s,e[2]=n[2]*s,e[3]=0,e[4]=n[4]*r,e[5]=n[5]*r,e[6]=n[6]*r,e[7]=0,e[8]=n[8]*a,e[9]=n[9]*a,e[10]=n[10]*a,e[11]=0,e[12]=0,e[13]=0,e[14]=0,e[15]=1,this}makeRotationFromEuler(t){const e=this.elements,n=t.x,s=t.y,r=t.z,a=Math.cos(n),o=Math.sin(n),l=Math.cos(s),h=Math.sin(s),d=Math.cos(r),c=Math.sin(r);if(t.order==="XYZ"){const u=a*d,f=a*c,g=o*d,v=o*c;e[0]=l*d,e[4]=-l*c,e[8]=h,e[1]=f+g*h,e[5]=u-v*h,e[9]=-o*l,e[2]=v-u*h,e[6]=g+f*h,e[10]=a*l}else if(t.order==="YXZ"){const u=l*d,f=l*c,g=h*d,v=h*c;e[0]=u+v*o,e[4]=g*o-f,e[8]=a*h,e[1]=a*c,e[5]=a*d,e[9]=-o,e[2]=f*o-g,e[6]=v+u*o,e[10]=a*l}else if(t.order==="ZXY"){const u=l*d,f=l*c,g=h*d,v=h*c;e[0]=u-v*o,e[4]=-a*c,e[8]=g+f*o,e[1]=f+g*o,e[5]=a*d,e[9]=v-u*o,e[2]=-a*h,e[6]=o,e[10]=a*l}else if(t.order==="ZYX"){const u=a*d,f=a*c,g=o*d,v=o*c;e[0]=l*d,e[4]=g*h-f,e[8]=u*h+v,e[1]=l*c,e[5]=v*h+u,e[9]=f*h-g,e[2]=-h,e[6]=o*l,e[10]=a*l}else if(t.order==="YZX"){const u=a*l,f=a*h,g=o*l,v=o*h;e[0]=l*d,e[4]=v-u*c,e[8]=g*c+f,e[1]=c,e[5]=a*d,e[9]=-o*d,e[2]=-h*d,e[6]=f*c+g,e[10]=u-v*c}else if(t.order==="XZY"){const u=a*l,f=a*h,g=o*l,v=o*h;e[0]=l*d,e[4]=-c,e[8]=h*d,e[1]=u*c+v,e[5]=a*d,e[9]=f*c-g,e[2]=g*c-f,e[6]=o*d,e[10]=v*c+u}return e[3]=0,e[7]=0,e[11]=0,e[12]=0,e[13]=0,e[14]=0,e[15]=1,this}makeRotationFromQuaternion(t){return this.compose(zh,t,Hh)}lookAt(t,e,n){const s=this.elements;return Oe.subVectors(t,e),Oe.lengthSq()===0&&(Oe.z=1),Oe.normalize(),bn.crossVectors(n,Oe),bn.lengthSq()===0&&(Math.abs(n.z)===1?Oe.x+=1e-4:Oe.z+=1e-4,Oe.normalize(),bn.crossVectors(n,Oe)),bn.normalize(),xs.crossVectors(Oe,bn),s[0]=bn.x,s[4]=xs.x,s[8]=Oe.x,s[1]=bn.y,s[5]=xs.y,s[9]=Oe.y,s[2]=bn.z,s[6]=xs.z,s[10]=Oe.z,this}multiply(t){return this.multiplyMatrices(this,t)}premultiply(t){return this.multiplyMatrices(t,this)}multiplyMatrices(t,e){const n=t.elements,s=e.elements,r=this.elements,a=n[0],o=n[4],l=n[8],h=n[12],d=n[1],c=n[5],u=n[9],f=n[13],g=n[2],v=n[6],m=n[10],p=n[14],y=n[3],_=n[7],S=n[11],P=n[15],T=s[0],A=s[4],L=s[8],q=s[12],x=s[1],E=s[5],z=s[9],V=s[13],K=s[2],G=s[6],I=s[10],F=s[14],O=s[3],Q=s[7],nt=s[11],rt=s[15];return r[0]=a*T+o*x+l*K+h*O,r[4]=a*A+o*E+l*G+h*Q,r[8]=a*L+o*z+l*I+h*nt,r[12]=a*q+o*V+l*F+h*rt,r[1]=d*T+c*x+u*K+f*O,r[5]=d*A+c*E+u*G+f*Q,r[9]=d*L+c*z+u*I+f*nt,r[13]=d*q+c*V+u*F+f*rt,r[2]=g*T+v*x+m*K+p*O,r[6]=g*A+v*E+m*G+p*Q,r[10]=g*L+v*z+m*I+p*nt,r[14]=g*q+v*V+m*F+p*rt,r[3]=y*T+_*x+S*K+P*O,r[7]=y*A+_*E+S*G+P*Q,r[11]=y*L+_*z+S*I+P*nt,r[15]=y*q+_*V+S*F+P*rt,this}multiplyScalar(t){const e=this.elements;return e[0]*=t,e[4]*=t,e[8]*=t,e[12]*=t,e[1]*=t,e[5]*=t,e[9]*=t,e[13]*=t,e[2]*=t,e[6]*=t,e[10]*=t,e[14]*=t,e[3]*=t,e[7]*=t,e[11]*=t,e[15]*=t,this}determinant(){const t=this.elements,e=t[0],n=t[4],s=t[8],r=t[12],a=t[1],o=t[5],l=t[9],h=t[13],d=t[2],c=t[6],u=t[10],f=t[14],g=t[3],v=t[7],m=t[11],p=t[15];return g*(+r*l*c-s*h*c-r*o*u+n*h*u+s*o*f-n*l*f)+v*(+e*l*f-e*h*u+r*a*u-s*a*f+s*h*d-r*l*d)+m*(+e*h*c-e*o*f-r*a*c+n*a*f+r*o*d-n*h*d)+p*(-s*o*d-e*l*c+e*o*u+s*a*c-n*a*u+n*l*d)}transpose(){const t=this.elements;let e;return e=t[1],t[1]=t[4],t[4]=e,e=t[2],t[2]=t[8],t[8]=e,e=t[6],t[6]=t[9],t[9]=e,e=t[3],t[3]=t[12],t[12]=e,e=t[7],t[7]=t[13],t[13]=e,e=t[11],t[11]=t[14],t[14]=e,this}setPosition(t,e,n){const s=this.elements;return t.isVector3?(s[12]=t.x,s[13]=t.y,s[14]=t.z):(s[12]=t,s[13]=e,s[14]=n),this}invert(){const t=this.elements,e=t[0],n=t[1],s=t[2],r=t[3],a=t[4],o=t[5],l=t[6],h=t[7],d=t[8],c=t[9],u=t[10],f=t[11],g=t[12],v=t[13],m=t[14],p=t[15],y=c*m*h-v*u*h+v*l*f-o*m*f-c*l*p+o*u*p,_=g*u*h-d*m*h-g*l*f+a*m*f+d*l*p-a*u*p,S=d*v*h-g*c*h+g*o*f-a*v*f-d*o*p+a*c*p,P=g*c*l-d*v*l-g*o*u+a*v*u+d*o*m-a*c*m,T=e*y+n*_+s*S+r*P;if(T===0)return this.set(0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0);const A=1/T;return t[0]=y*A,t[1]=(v*u*r-c*m*r-v*s*f+n*m*f+c*s*p-n*u*p)*A,t[2]=(o*m*r-v*l*r+v*s*h-n*m*h-o*s*p+n*l*p)*A,t[3]=(c*l*r-o*u*r-c*s*h+n*u*h+o*s*f-n*l*f)*A,t[4]=_*A,t[5]=(d*m*r-g*u*r+g*s*f-e*m*f-d*s*p+e*u*p)*A,t[6]=(g*l*r-a*m*r-g*s*h+e*m*h+a*s*p-e*l*p)*A,t[7]=(a*u*r-d*l*r+d*s*h-e*u*h-a*s*f+e*l*f)*A,t[8]=S*A,t[9]=(g*c*r-d*v*r-g*n*f+e*v*f+d*n*p-e*c*p)*A,t[10]=(a*v*r-g*o*r+g*n*h-e*v*h-a*n*p+e*o*p)*A,t[11]=(d*o*r-a*c*r-d*n*h+e*c*h+a*n*f-e*o*f)*A,t[12]=P*A,t[13]=(d*v*s-g*c*s+g*n*u-e*v*u-d*n*m+e*c*m)*A,t[14]=(g*o*s-a*v*s-g*n*l+e*v*l+a*n*m-e*o*m)*A,t[15]=(a*c*s-d*o*s+d*n*l-e*c*l-a*n*u+e*o*u)*A,this}scale(t){const e=this.elements,n=t.x,s=t.y,r=t.z;return e[0]*=n,e[4]*=s,e[8]*=r,e[1]*=n,e[5]*=s,e[9]*=r,e[2]*=n,e[6]*=s,e[10]*=r,e[3]*=n,e[7]*=s,e[11]*=r,this}getMaxScaleOnAxis(){const t=this.elements,e=t[0]*t[0]+t[1]*t[1]+t[2]*t[2],n=t[4]*t[4]+t[5]*t[5]+t[6]*t[6],s=t[8]*t[8]+t[9]*t[9]+t[10]*t[10];return Math.sqrt(Math.max(e,n,s))}makeTranslation(t,e,n){return t.isVector3?this.set(1,0,0,t.x,0,1,0,t.y,0,0,1,t.z,0,0,0,1):this.set(1,0,0,t,0,1,0,e,0,0,1,n,0,0,0,1),this}makeRotationX(t){const e=Math.cos(t),n=Math.sin(t);return this.set(1,0,0,0,0,e,-n,0,0,n,e,0,0,0,0,1),this}makeRotationY(t){const e=Math.cos(t),n=Math.sin(t);return this.set(e,0,n,0,0,1,0,0,-n,0,e,0,0,0,0,1),this}makeRotationZ(t){const e=Math.cos(t),n=Math.sin(t);return this.set(e,-n,0,0,n,e,0,0,0,0,1,0,0,0,0,1),this}makeRotationAxis(t,e){const n=Math.cos(e),s=Math.sin(e),r=1-n,a=t.x,o=t.y,l=t.z,h=r*a,d=r*o;return this.set(h*a+n,h*o-s*l,h*l+s*o,0,h*o+s*l,d*o+n,d*l-s*a,0,h*l-s*o,d*l+s*a,r*l*l+n,0,0,0,0,1),this}makeScale(t,e,n){return this.set(t,0,0,0,0,e,0,0,0,0,n,0,0,0,0,1),this}makeShear(t,e,n,s,r,a){return this.set(1,n,r,0,t,1,a,0,e,s,1,0,0,0,0,1),this}compose(t,e,n){const s=this.elements,r=e._x,a=e._y,o=e._z,l=e._w,h=r+r,d=a+a,c=o+o,u=r*h,f=r*d,g=r*c,v=a*d,m=a*c,p=o*c,y=l*h,_=l*d,S=l*c,P=n.x,T=n.y,A=n.z;return s[0]=(1-(v+p))*P,s[1]=(f+S)*P,s[2]=(g-_)*P,s[3]=0,s[4]=(f-S)*T,s[5]=(1-(u+p))*T,s[6]=(m+y)*T,s[7]=0,s[8]=(g+_)*A,s[9]=(m-y)*A,s[10]=(1-(u+v))*A,s[11]=0,s[12]=t.x,s[13]=t.y,s[14]=t.z,s[15]=1,this}decompose(t,e,n){const s=this.elements;let r=oi.set(s[0],s[1],s[2]).length();const a=oi.set(s[4],s[5],s[6]).length(),o=oi.set(s[8],s[9],s[10]).length();this.determinant()<0&&(r=-r),t.x=s[12],t.y=s[13],t.z=s[14],Qe.copy(this);const h=1/r,d=1/a,c=1/o;return Qe.elements[0]*=h,Qe.elements[1]*=h,Qe.elements[2]*=h,Qe.elements[4]*=d,Qe.elements[5]*=d,Qe.elements[6]*=d,Qe.elements[8]*=c,Qe.elements[9]*=c,Qe.elements[10]*=c,e.setFromRotationMatrix(Qe),n.x=r,n.y=a,n.z=o,this}makePerspective(t,e,n,s,r,a,o=vn){const l=this.elements,h=2*r/(e-t),d=2*r/(n-s),c=(e+t)/(e-t),u=(n+s)/(n-s);let f,g;if(o===vn)f=-(a+r)/(a-r),g=-2*a*r/(a-r);else if(o===$s)f=-a/(a-r),g=-a*r/(a-r);else throw new Error("THREE.Matrix4.makePerspective(): Invalid coordinate system: "+o);return l[0]=h,l[4]=0,l[8]=c,l[12]=0,l[1]=0,l[5]=d,l[9]=u,l[13]=0,l[2]=0,l[6]=0,l[10]=f,l[14]=g,l[3]=0,l[7]=0,l[11]=-1,l[15]=0,this}makeOrthographic(t,e,n,s,r,a,o=vn){const l=this.elements,h=1/(e-t),d=1/(n-s),c=1/(a-r),u=(e+t)*h,f=(n+s)*d;let g,v;if(o===vn)g=(a+r)*c,v=-2*c;else if(o===$s)g=r*c,v=-1*c;else throw new Error("THREE.Matrix4.makeOrthographic(): Invalid coordinate system: "+o);return l[0]=2*h,l[4]=0,l[8]=0,l[12]=-u,l[1]=0,l[5]=2*d,l[9]=0,l[13]=-f,l[2]=0,l[6]=0,l[10]=v,l[14]=-g,l[3]=0,l[7]=0,l[11]=0,l[15]=1,this}equals(t){const e=this.elements,n=t.elements;for(let s=0;s<16;s++)if(e[s]!==n[s])return!1;return!0}fromArray(t,e=0){for(let n=0;n<16;n++)this.elements[n]=t[n+e];return this}toArray(t=[],e=0){const n=this.elements;return t[e]=n[0],t[e+1]=n[1],t[e+2]=n[2],t[e+3]=n[3],t[e+4]=n[4],t[e+5]=n[5],t[e+6]=n[6],t[e+7]=n[7],t[e+8]=n[8],t[e+9]=n[9],t[e+10]=n[10],t[e+11]=n[11],t[e+12]=n[12],t[e+13]=n[13],t[e+14]=n[14],t[e+15]=n[15],t}}const oi=new R,Qe=new ee,zh=new R(0,0,0),Hh=new R(1,1,1),bn=new R,xs=new R,Oe=new R,xo=new ee,vo=new ls;class on{constructor(t=0,e=0,n=0,s=on.DEFAULT_ORDER){this.isEuler=!0,this._x=t,this._y=e,this._z=n,this._order=s}get x(){return this._x}set x(t){this._x=t,this._onChangeCallback()}get y(){return this._y}set y(t){this._y=t,this._onChangeCallback()}get z(){return this._z}set z(t){this._z=t,this._onChangeCallback()}get order(){return this._order}set order(t){this._order=t,this._onChangeCallback()}set(t,e,n,s=this._order){return this._x=t,this._y=e,this._z=n,this._order=s,this._onChangeCallback(),this}clone(){return new this.constructor(this._x,this._y,this._z,this._order)}copy(t){return this._x=t._x,this._y=t._y,this._z=t._z,this._order=t._order,this._onChangeCallback(),this}setFromRotationMatrix(t,e=this._order,n=!0){const s=t.elements,r=s[0],a=s[4],o=s[8],l=s[1],h=s[5],d=s[9],c=s[2],u=s[6],f=s[10];switch(e){case"XYZ":this._y=Math.asin(Ee(o,-1,1)),Math.abs(o)<.9999999?(this._x=Math.atan2(-d,f),this._z=Math.atan2(-a,r)):(this._x=Math.atan2(u,h),this._z=0);break;case"YXZ":this._x=Math.asin(-Ee(d,-1,1)),Math.abs(d)<.9999999?(this._y=Math.atan2(o,f),this._z=Math.atan2(l,h)):(this._y=Math.atan2(-c,r),this._z=0);break;case"ZXY":this._x=Math.asin(Ee(u,-1,1)),Math.abs(u)<.9999999?(this._y=Math.atan2(-c,f),this._z=Math.atan2(-a,h)):(this._y=0,this._z=Math.atan2(l,r));break;case"ZYX":this._y=Math.asin(-Ee(c,-1,1)),Math.abs(c)<.9999999?(this._x=Math.atan2(u,f),this._z=Math.atan2(l,r)):(this._x=0,this._z=Math.atan2(-a,h));break;case"YZX":this._z=Math.asin(Ee(l,-1,1)),Math.abs(l)<.9999999?(this._x=Math.atan2(-d,h),this._y=Math.atan2(-c,r)):(this._x=0,this._y=Math.atan2(o,f));break;case"XZY":this._z=Math.asin(-Ee(a,-1,1)),Math.abs(a)<.9999999?(this._x=Math.atan2(u,h),this._y=Math.atan2(o,r)):(this._x=Math.atan2(-d,f),this._y=0);break;default:console.warn("THREE.Euler: .setFromRotationMatrix() encountered an unknown order: "+e)}return this._order=e,n===!0&&this._onChangeCallback(),this}setFromQuaternion(t,e,n){return xo.makeRotationFromQuaternion(t),this.setFromRotationMatrix(xo,e,n)}setFromVector3(t,e=this._order){return this.set(t.x,t.y,t.z,e)}reorder(t){return vo.setFromEuler(this),this.setFromQuaternion(vo,t)}equals(t){return t._x===this._x&&t._y===this._y&&t._z===this._z&&t._order===this._order}fromArray(t){return this._x=t[0],this._y=t[1],this._z=t[2],t[3]!==void 0&&(this._order=t[3]),this._onChangeCallback(),this}toArray(t=[],e=0){return t[e]=this._x,t[e+1]=this._y,t[e+2]=this._z,t[e+3]=this._order,t}_onChange(t){return this._onChangeCallback=t,this}_onChangeCallback(){}*[Symbol.iterator](){yield this._x,yield this._y,yield this._z,yield this._order}}on.DEFAULT_ORDER="XYZ";class Ya{constructor(){this.mask=1}set(t){this.mask=(1<<t|0)>>>0}enable(t){this.mask|=1<<t|0}enableAll(){this.mask=-1}toggle(t){this.mask^=1<<t|0}disable(t){this.mask&=~(1<<t|0)}disableAll(){this.mask=0}test(t){return(this.mask&t.mask)!==0}isEnabled(t){return(this.mask&(1<<t|0))!==0}}let Gh=0;const Mo=new R,li=new ls,pn=new ee,vs=new R,Vi=new R,Vh=new R,Wh=new ls,yo=new R(1,0,0),So=new R(0,1,0),wo=new R(0,0,1),Eo={type:"added"},Xh={type:"removed"},ci={type:"childadded",child:null},Sr={type:"childremoved",child:null};class me extends Ni{constructor(){super(),this.isObject3D=!0,Object.defineProperty(this,"id",{value:Gh++}),this.uuid=Fi(),this.name="",this.type="Object3D",this.parent=null,this.children=[],this.up=me.DEFAULT_UP.clone();const t=new R,e=new on,n=new ls,s=new R(1,1,1);function r(){n.setFromEuler(e,!1)}function a(){e.setFromQuaternion(n,void 0,!1)}e._onChange(r),n._onChange(a),Object.defineProperties(this,{position:{configurable:!0,enumerable:!0,value:t},rotation:{configurable:!0,enumerable:!0,value:e},quaternion:{configurable:!0,enumerable:!0,value:n},scale:{configurable:!0,enumerable:!0,value:s},modelViewMatrix:{value:new ee},normalMatrix:{value:new Ot}}),this.matrix=new ee,this.matrixWorld=new ee,this.matrixAutoUpdate=me.DEFAULT_MATRIX_AUTO_UPDATE,this.matrixWorldAutoUpdate=me.DEFAULT_MATRIX_WORLD_AUTO_UPDATE,this.matrixWorldNeedsUpdate=!1,this.layers=new Ya,this.visible=!0,this.castShadow=!1,this.receiveShadow=!1,this.frustumCulled=!0,this.renderOrder=0,this.animations=[],this.userData={}}onBeforeShadow(){}onAfterShadow(){}onBeforeRender(){}onAfterRender(){}applyMatrix4(t){this.matrixAutoUpdate&&this.updateMatrix(),this.matrix.premultiply(t),this.matrix.decompose(this.position,this.quaternion,this.scale)}applyQuaternion(t){return this.quaternion.premultiply(t),this}setRotationFromAxisAngle(t,e){this.quaternion.setFromAxisAngle(t,e)}setRotationFromEuler(t){this.quaternion.setFromEuler(t,!0)}setRotationFromMatrix(t){this.quaternion.setFromRotationMatrix(t)}setRotationFromQuaternion(t){this.quaternion.copy(t)}rotateOnAxis(t,e){return li.setFromAxisAngle(t,e),this.quaternion.multiply(li),this}rotateOnWorldAxis(t,e){return li.setFromAxisAngle(t,e),this.quaternion.premultiply(li),this}rotateX(t){return this.rotateOnAxis(yo,t)}rotateY(t){return this.rotateOnAxis(So,t)}rotateZ(t){return this.rotateOnAxis(wo,t)}translateOnAxis(t,e){return Mo.copy(t).applyQuaternion(this.quaternion),this.position.add(Mo.multiplyScalar(e)),this}translateX(t){return this.translateOnAxis(yo,t)}translateY(t){return this.translateOnAxis(So,t)}translateZ(t){return this.translateOnAxis(wo,t)}localToWorld(t){return this.updateWorldMatrix(!0,!1),t.applyMatrix4(this.matrixWorld)}worldToLocal(t){return this.updateWorldMatrix(!0,!1),t.applyMatrix4(pn.copy(this.matrixWorld).invert())}lookAt(t,e,n){t.isVector3?vs.copy(t):vs.set(t,e,n);const s=this.parent;this.updateWorldMatrix(!0,!1),Vi.setFromMatrixPosition(this.matrixWorld),this.isCamera||this.isLight?pn.lookAt(Vi,vs,this.up):pn.lookAt(vs,Vi,this.up),this.quaternion.setFromRotationMatrix(pn),s&&(pn.extractRotation(s.matrixWorld),li.setFromRotationMatrix(pn),this.quaternion.premultiply(li.invert()))}add(t){if(arguments.length>1){for(let e=0;e<arguments.length;e++)this.add(arguments[e]);return this}return t===this?(console.error("THREE.Object3D.add: object can't be added as a child of itself.",t),this):(t&&t.isObject3D?(t.removeFromParent(),t.parent=this,this.children.push(t),t.dispatchEvent(Eo),ci.child=t,this.dispatchEvent(ci),ci.child=null):console.error("THREE.Object3D.add: object not an instance of THREE.Object3D.",t),this)}remove(t){if(arguments.length>1){for(let n=0;n<arguments.length;n++)this.remove(arguments[n]);return this}const e=this.children.indexOf(t);return e!==-1&&(t.parent=null,this.children.splice(e,1),t.dispatchEvent(Xh),Sr.child=t,this.dispatchEvent(Sr),Sr.child=null),this}removeFromParent(){const t=this.parent;return t!==null&&t.remove(this),this}clear(){return this.remove(...this.children)}attach(t){return this.updateWorldMatrix(!0,!1),pn.copy(this.matrixWorld).invert(),t.parent!==null&&(t.parent.updateWorldMatrix(!0,!1),pn.multiply(t.parent.matrixWorld)),t.applyMatrix4(pn),t.removeFromParent(),t.parent=this,this.children.push(t),t.updateWorldMatrix(!1,!0),t.dispatchEvent(Eo),ci.child=t,this.dispatchEvent(ci),ci.child=null,this}getObjectById(t){return this.getObjectByProperty("id",t)}getObjectByName(t){return this.getObjectByProperty("name",t)}getObjectByProperty(t,e){if(this[t]===e)return this;for(let n=0,s=this.children.length;n<s;n++){const a=this.children[n].getObjectByProperty(t,e);if(a!==void 0)return a}}getObjectsByProperty(t,e,n=[]){this[t]===e&&n.push(this);const s=this.children;for(let r=0,a=s.length;r<a;r++)s[r].getObjectsByProperty(t,e,n);return n}getWorldPosition(t){return this.updateWorldMatrix(!0,!1),t.setFromMatrixPosition(this.matrixWorld)}getWorldQuaternion(t){return this.updateWorldMatrix(!0,!1),this.matrixWorld.decompose(Vi,t,Vh),t}getWorldScale(t){return this.updateWorldMatrix(!0,!1),this.matrixWorld.decompose(Vi,Wh,t),t}getWorldDirection(t){this.updateWorldMatrix(!0,!1);const e=this.matrixWorld.elements;return t.set(e[8],e[9],e[10]).normalize()}raycast(){}traverse(t){t(this);const e=this.children;for(let n=0,s=e.length;n<s;n++)e[n].traverse(t)}traverseVisible(t){if(this.visible===!1)return;t(this);const e=this.children;for(let n=0,s=e.length;n<s;n++)e[n].traverseVisible(t)}traverseAncestors(t){const e=this.parent;e!==null&&(t(e),e.traverseAncestors(t))}updateMatrix(){this.matrix.compose(this.position,this.quaternion,this.scale),this.matrixWorldNeedsUpdate=!0}updateMatrixWorld(t){this.matrixAutoUpdate&&this.updateMatrix(),(this.matrixWorldNeedsUpdate||t)&&(this.matrixWorldAutoUpdate===!0&&(this.parent===null?this.matrixWorld.copy(this.matrix):this.matrixWorld.multiplyMatrices(this.parent.matrixWorld,this.matrix)),this.matrixWorldNeedsUpdate=!1,t=!0);const e=this.children;for(let n=0,s=e.length;n<s;n++)e[n].updateMatrixWorld(t)}updateWorldMatrix(t,e){const n=this.parent;if(t===!0&&n!==null&&n.updateWorldMatrix(!0,!1),this.matrixAutoUpdate&&this.updateMatrix(),this.matrixWorldAutoUpdate===!0&&(this.parent===null?this.matrixWorld.copy(this.matrix):this.matrixWorld.multiplyMatrices(this.parent.matrixWorld,this.matrix)),e===!0){const s=this.children;for(let r=0,a=s.length;r<a;r++)s[r].updateWorldMatrix(!1,!0)}}toJSON(t){const e=t===void 0||typeof t=="string",n={};e&&(t={geometries:{},materials:{},textures:{},images:{},shapes:{},skeletons:{},animations:{},nodes:{}},n.metadata={version:4.6,type:"Object",generator:"Object3D.toJSON"});const s={};s.uuid=this.uuid,s.type=this.type,this.name!==""&&(s.name=this.name),this.castShadow===!0&&(s.castShadow=!0),this.receiveShadow===!0&&(s.receiveShadow=!0),this.visible===!1&&(s.visible=!1),this.frustumCulled===!1&&(s.frustumCulled=!1),this.renderOrder!==0&&(s.renderOrder=this.renderOrder),Object.keys(this.userData).length>0&&(s.userData=this.userData),s.layers=this.layers.mask,s.matrix=this.matrix.toArray(),s.up=this.up.toArray(),this.matrixAutoUpdate===!1&&(s.matrixAutoUpdate=!1),this.isInstancedMesh&&(s.type="InstancedMesh",s.count=this.count,s.instanceMatrix=this.instanceMatrix.toJSON(),this.instanceColor!==null&&(s.instanceColor=this.instanceColor.toJSON())),this.isBatchedMesh&&(s.type="BatchedMesh",s.perObjectFrustumCulled=this.perObjectFrustumCulled,s.sortObjects=this.sortObjects,s.drawRanges=this._drawRanges,s.reservedRanges=this._reservedRanges,s.visibility=this._visibility,s.active=this._active,s.bounds=this._bounds.map(o=>({boxInitialized:o.boxInitialized,boxMin:o.box.min.toArray(),boxMax:o.box.max.toArray(),sphereInitialized:o.sphereInitialized,sphereRadius:o.sphere.radius,sphereCenter:o.sphere.center.toArray()})),s.maxInstanceCount=this._maxInstanceCount,s.maxVertexCount=this._maxVertexCount,s.maxIndexCount=this._maxIndexCount,s.geometryInitialized=this._geometryInitialized,s.geometryCount=this._geometryCount,s.matricesTexture=this._matricesTexture.toJSON(t),this._colorsTexture!==null&&(s.colorsTexture=this._colorsTexture.toJSON(t)),this.boundingSphere!==null&&(s.boundingSphere={center:s.boundingSphere.center.toArray(),radius:s.boundingSphere.radius}),this.boundingBox!==null&&(s.boundingBox={min:s.boundingBox.min.toArray(),max:s.boundingBox.max.toArray()}));function r(o,l){return o[l.uuid]===void 0&&(o[l.uuid]=l.toJSON(t)),l.uuid}if(this.isScene)this.background&&(this.background.isColor?s.background=this.background.toJSON():this.background.isTexture&&(s.background=this.background.toJSON(t).uuid)),this.environment&&this.environment.isTexture&&this.environment.isRenderTargetTexture!==!0&&(s.environment=this.environment.toJSON(t).uuid);else if(this.isMesh||this.isLine||this.isPoints){s.geometry=r(t.geometries,this.geometry);const o=this.geometry.parameters;if(o!==void 0&&o.shapes!==void 0){const l=o.shapes;if(Array.isArray(l))for(let h=0,d=l.length;h<d;h++){const c=l[h];r(t.shapes,c)}else r(t.shapes,l)}}if(this.isSkinnedMesh&&(s.bindMode=this.bindMode,s.bindMatrix=this.bindMatrix.toArray(),this.skeleton!==void 0&&(r(t.skeletons,this.skeleton),s.skeleton=this.skeleton.uuid)),this.material!==void 0)if(Array.isArray(this.material)){const o=[];for(let l=0,h=this.material.length;l<h;l++)o.push(r(t.materials,this.material[l]));s.material=o}else s.material=r(t.materials,this.material);if(this.children.length>0){s.children=[];for(let o=0;o<this.children.length;o++)s.children.push(this.children[o].toJSON(t).object)}if(this.animations.length>0){s.animations=[];for(let o=0;o<this.animations.length;o++){const l=this.animations[o];s.animations.push(r(t.animations,l))}}if(e){const o=a(t.geometries),l=a(t.materials),h=a(t.textures),d=a(t.images),c=a(t.shapes),u=a(t.skeletons),f=a(t.animations),g=a(t.nodes);o.length>0&&(n.geometries=o),l.length>0&&(n.materials=l),h.length>0&&(n.textures=h),d.length>0&&(n.images=d),c.length>0&&(n.shapes=c),u.length>0&&(n.skeletons=u),f.length>0&&(n.animations=f),g.length>0&&(n.nodes=g)}return n.object=s,n;function a(o){const l=[];for(const h in o){const d=o[h];delete d.metadata,l.push(d)}return l}}clone(t){return new this.constructor().copy(this,t)}copy(t,e=!0){if(this.name=t.name,this.up.copy(t.up),this.position.copy(t.position),this.rotation.order=t.rotation.order,this.quaternion.copy(t.quaternion),this.scale.copy(t.scale),this.matrix.copy(t.matrix),this.matrixWorld.copy(t.matrixWorld),this.matrixAutoUpdate=t.matrixAutoUpdate,this.matrixWorldAutoUpdate=t.matrixWorldAutoUpdate,this.matrixWorldNeedsUpdate=t.matrixWorldNeedsUpdate,this.layers.mask=t.layers.mask,this.visible=t.visible,this.castShadow=t.castShadow,this.receiveShadow=t.receiveShadow,this.frustumCulled=t.frustumCulled,this.renderOrder=t.renderOrder,this.animations=t.animations.slice(),this.userData=JSON.parse(JSON.stringify(t.userData)),e===!0)for(let n=0;n<t.children.length;n++){const s=t.children[n];this.add(s.clone())}return this}}me.DEFAULT_UP=new R(0,1,0);me.DEFAULT_MATRIX_AUTO_UPDATE=!0;me.DEFAULT_MATRIX_WORLD_AUTO_UPDATE=!0;const tn=new R,mn=new R,wr=new R,gn=new R,hi=new R,ui=new R,bo=new R,Er=new R,br=new R,Tr=new R,Ar=new te,Rr=new te,Cr=new te;class nn{constructor(t=new R,e=new R,n=new R){this.a=t,this.b=e,this.c=n}static getNormal(t,e,n,s){s.subVectors(n,e),tn.subVectors(t,e),s.cross(tn);const r=s.lengthSq();return r>0?s.multiplyScalar(1/Math.sqrt(r)):s.set(0,0,0)}static getBarycoord(t,e,n,s,r){tn.subVectors(s,e),mn.subVectors(n,e),wr.subVectors(t,e);const a=tn.dot(tn),o=tn.dot(mn),l=tn.dot(wr),h=mn.dot(mn),d=mn.dot(wr),c=a*h-o*o;if(c===0)return r.set(0,0,0),null;const u=1/c,f=(h*l-o*d)*u,g=(a*d-o*l)*u;return r.set(1-f-g,g,f)}static containsPoint(t,e,n,s){return this.getBarycoord(t,e,n,s,gn)===null?!1:gn.x>=0&&gn.y>=0&&gn.x+gn.y<=1}static getInterpolation(t,e,n,s,r,a,o,l){return this.getBarycoord(t,e,n,s,gn)===null?(l.x=0,l.y=0,"z"in l&&(l.z=0),"w"in l&&(l.w=0),null):(l.setScalar(0),l.addScaledVector(r,gn.x),l.addScaledVector(a,gn.y),l.addScaledVector(o,gn.z),l)}static getInterpolatedAttribute(t,e,n,s,r,a){return Ar.setScalar(0),Rr.setScalar(0),Cr.setScalar(0),Ar.fromBufferAttribute(t,e),Rr.fromBufferAttribute(t,n),Cr.fromBufferAttribute(t,s),a.setScalar(0),a.addScaledVector(Ar,r.x),a.addScaledVector(Rr,r.y),a.addScaledVector(Cr,r.z),a}static isFrontFacing(t,e,n,s){return tn.subVectors(n,e),mn.subVectors(t,e),tn.cross(mn).dot(s)<0}set(t,e,n){return this.a.copy(t),this.b.copy(e),this.c.copy(n),this}setFromPointsAndIndices(t,e,n,s){return this.a.copy(t[e]),this.b.copy(t[n]),this.c.copy(t[s]),this}setFromAttributeAndIndices(t,e,n,s){return this.a.fromBufferAttribute(t,e),this.b.fromBufferAttribute(t,n),this.c.fromBufferAttribute(t,s),this}clone(){return new this.constructor().copy(this)}copy(t){return this.a.copy(t.a),this.b.copy(t.b),this.c.copy(t.c),this}getArea(){return tn.subVectors(this.c,this.b),mn.subVectors(this.a,this.b),tn.cross(mn).length()*.5}getMidpoint(t){return t.addVectors(this.a,this.b).add(this.c).multiplyScalar(1/3)}getNormal(t){return nn.getNormal(this.a,this.b,this.c,t)}getPlane(t){return t.setFromCoplanarPoints(this.a,this.b,this.c)}getBarycoord(t,e){return nn.getBarycoord(t,this.a,this.b,this.c,e)}getInterpolation(t,e,n,s,r){return nn.getInterpolation(t,this.a,this.b,this.c,e,n,s,r)}containsPoint(t){return nn.containsPoint(t,this.a,this.b,this.c)}isFrontFacing(t){return nn.isFrontFacing(this.a,this.b,this.c,t)}intersectsBox(t){return t.intersectsTriangle(this)}closestPointToPoint(t,e){const n=this.a,s=this.b,r=this.c;let a,o;hi.subVectors(s,n),ui.subVectors(r,n),Er.subVectors(t,n);const l=hi.dot(Er),h=ui.dot(Er);if(l<=0&&h<=0)return e.copy(n);br.subVectors(t,s);const d=hi.dot(br),c=ui.dot(br);if(d>=0&&c<=d)return e.copy(s);const u=l*c-d*h;if(u<=0&&l>=0&&d<=0)return a=l/(l-d),e.copy(n).addScaledVector(hi,a);Tr.subVectors(t,r);const f=hi.dot(Tr),g=ui.dot(Tr);if(g>=0&&f<=g)return e.copy(r);const v=f*h-l*g;if(v<=0&&h>=0&&g<=0)return o=h/(h-g),e.copy(n).addScaledVector(ui,o);const m=d*g-f*c;if(m<=0&&c-d>=0&&f-g>=0)return bo.subVectors(r,s),o=(c-d)/(c-d+(f-g)),e.copy(s).addScaledVector(bo,o);const p=1/(m+v+u);return a=v*p,o=u*p,e.copy(n).addScaledVector(hi,a).addScaledVector(ui,o)}equals(t){return t.a.equals(this.a)&&t.b.equals(this.b)&&t.c.equals(this.c)}}const Kl={aliceblue:15792383,antiquewhite:16444375,aqua:65535,aquamarine:8388564,azure:15794175,beige:16119260,bisque:16770244,black:0,blanchedalmond:16772045,blue:255,blueviolet:9055202,brown:10824234,burlywood:14596231,cadetblue:6266528,chartreuse:8388352,chocolate:13789470,coral:16744272,cornflowerblue:6591981,cornsilk:16775388,crimson:14423100,cyan:65535,darkblue:139,darkcyan:35723,darkgoldenrod:12092939,darkgray:11119017,darkgreen:25600,darkgrey:11119017,darkkhaki:12433259,darkmagenta:9109643,darkolivegreen:5597999,darkorange:16747520,darkorchid:10040012,darkred:9109504,darksalmon:15308410,darkseagreen:9419919,darkslateblue:4734347,darkslategray:3100495,darkslategrey:3100495,darkturquoise:52945,darkviolet:9699539,deeppink:16716947,deepskyblue:49151,dimgray:6908265,dimgrey:6908265,dodgerblue:2003199,firebrick:11674146,floralwhite:16775920,forestgreen:2263842,fuchsia:16711935,gainsboro:14474460,ghostwhite:16316671,gold:16766720,goldenrod:14329120,gray:8421504,green:32768,greenyellow:11403055,grey:8421504,honeydew:15794160,hotpink:16738740,indianred:13458524,indigo:4915330,ivory:16777200,khaki:15787660,lavender:15132410,lavenderblush:16773365,lawngreen:8190976,lemonchiffon:16775885,lightblue:11393254,lightcoral:15761536,lightcyan:14745599,lightgoldenrodyellow:16448210,lightgray:13882323,lightgreen:9498256,lightgrey:13882323,lightpink:16758465,lightsalmon:16752762,lightseagreen:2142890,lightskyblue:8900346,lightslategray:7833753,lightslategrey:7833753,lightsteelblue:11584734,lightyellow:16777184,lime:65280,limegreen:3329330,linen:16445670,magenta:16711935,maroon:8388608,mediumaquamarine:6737322,mediumblue:205,mediumorchid:12211667,mediumpurple:9662683,mediumseagreen:3978097,mediumslateblue:8087790,mediumspringgreen:64154,mediumturquoise:4772300,mediumvioletred:13047173,midnightblue:1644912,mintcream:16121850,mistyrose:16770273,moccasin:16770229,navajowhite:16768685,navy:128,oldlace:16643558,olive:8421376,olivedrab:7048739,orange:16753920,orangered:16729344,orchid:14315734,palegoldenrod:15657130,palegreen:10025880,paleturquoise:11529966,palevioletred:14381203,papayawhip:16773077,peachpuff:16767673,peru:13468991,pink:16761035,plum:14524637,powderblue:11591910,purple:8388736,rebeccapurple:6697881,red:16711680,rosybrown:12357519,royalblue:4286945,saddlebrown:9127187,salmon:16416882,sandybrown:16032864,seagreen:3050327,seashell:16774638,sienna:10506797,silver:12632256,skyblue:8900331,slateblue:6970061,slategray:7372944,slategrey:7372944,snow:16775930,springgreen:65407,steelblue:4620980,tan:13808780,teal:32896,thistle:14204888,tomato:16737095,turquoise:4251856,violet:15631086,wheat:16113331,white:16777215,whitesmoke:16119285,yellow:16776960,yellowgreen:10145074},Tn={h:0,s:0,l:0},Ms={h:0,s:0,l:0};function Pr(i,t,e){return e<0&&(e+=1),e>1&&(e-=1),e<1/6?i+(t-i)*6*e:e<1/2?t:e<2/3?i+(t-i)*6*(2/3-e):i}class Pt{constructor(t,e,n){return this.isColor=!0,this.r=1,this.g=1,this.b=1,this.set(t,e,n)}set(t,e,n){if(e===void 0&&n===void 0){const s=t;s&&s.isColor?this.copy(s):typeof s=="number"?this.setHex(s):typeof s=="string"&&this.setStyle(s)}else this.setRGB(t,e,n);return this}setScalar(t){return this.r=t,this.g=t,this.b=t,this}setHex(t,e=je){return t=Math.floor(t),this.r=(t>>16&255)/255,this.g=(t>>8&255)/255,this.b=(t&255)/255,Jt.toWorkingColorSpace(this,e),this}setRGB(t,e,n,s=Jt.workingColorSpace){return this.r=t,this.g=e,this.b=n,Jt.toWorkingColorSpace(this,s),this}setHSL(t,e,n,s=Jt.workingColorSpace){if(t=Wa(t,1),e=Ee(e,0,1),n=Ee(n,0,1),e===0)this.r=this.g=this.b=n;else{const r=n<=.5?n*(1+e):n+e-n*e,a=2*n-r;this.r=Pr(a,r,t+1/3),this.g=Pr(a,r,t),this.b=Pr(a,r,t-1/3)}return Jt.toWorkingColorSpace(this,s),this}setStyle(t,e=je){function n(r){r!==void 0&&parseFloat(r)<1&&console.warn("THREE.Color: Alpha component of "+t+" will be ignored.")}let s;if(s=/^(\w+)\(([^\)]*)\)/.exec(t)){let r;const a=s[1],o=s[2];switch(a){case"rgb":case"rgba":if(r=/^\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*(\d*\.?\d+)\s*)?$/.exec(o))return n(r[4]),this.setRGB(Math.min(255,parseInt(r[1],10))/255,Math.min(255,parseInt(r[2],10))/255,Math.min(255,parseInt(r[3],10))/255,e);if(r=/^\s*(\d+)\%\s*,\s*(\d+)\%\s*,\s*(\d+)\%\s*(?:,\s*(\d*\.?\d+)\s*)?$/.exec(o))return n(r[4]),this.setRGB(Math.min(100,parseInt(r[1],10))/100,Math.min(100,parseInt(r[2],10))/100,Math.min(100,parseInt(r[3],10))/100,e);break;case"hsl":case"hsla":if(r=/^\s*(\d*\.?\d+)\s*,\s*(\d*\.?\d+)\%\s*,\s*(\d*\.?\d+)\%\s*(?:,\s*(\d*\.?\d+)\s*)?$/.exec(o))return n(r[4]),this.setHSL(parseFloat(r[1])/360,parseFloat(r[2])/100,parseFloat(r[3])/100,e);break;default:console.warn("THREE.Color: Unknown color model "+t)}}else if(s=/^\#([A-Fa-f\d]+)$/.exec(t)){const r=s[1],a=r.length;if(a===3)return this.setRGB(parseInt(r.charAt(0),16)/15,parseInt(r.charAt(1),16)/15,parseInt(r.charAt(2),16)/15,e);if(a===6)return this.setHex(parseInt(r,16),e);console.warn("THREE.Color: Invalid hex color "+t)}else if(t&&t.length>0)return this.setColorName(t,e);return this}setColorName(t,e=je){const n=Kl[t.toLowerCase()];return n!==void 0?this.setHex(n,e):console.warn("THREE.Color: Unknown color "+t),this}clone(){return new this.constructor(this.r,this.g,this.b)}copy(t){return this.r=t.r,this.g=t.g,this.b=t.b,this}copySRGBToLinear(t){return this.r=Ti(t.r),this.g=Ti(t.g),this.b=Ti(t.b),this}copyLinearToSRGB(t){return this.r=pr(t.r),this.g=pr(t.g),this.b=pr(t.b),this}convertSRGBToLinear(){return this.copySRGBToLinear(this),this}convertLinearToSRGB(){return this.copyLinearToSRGB(this),this}getHex(t=je){return Jt.fromWorkingColorSpace(we.copy(this),t),Math.round(Ee(we.r*255,0,255))*65536+Math.round(Ee(we.g*255,0,255))*256+Math.round(Ee(we.b*255,0,255))}getHexString(t=je){return("000000"+this.getHex(t).toString(16)).slice(-6)}getHSL(t,e=Jt.workingColorSpace){Jt.fromWorkingColorSpace(we.copy(this),e);const n=we.r,s=we.g,r=we.b,a=Math.max(n,s,r),o=Math.min(n,s,r);let l,h;const d=(o+a)/2;if(o===a)l=0,h=0;else{const c=a-o;switch(h=d<=.5?c/(a+o):c/(2-a-o),a){case n:l=(s-r)/c+(s<r?6:0);break;case s:l=(r-n)/c+2;break;case r:l=(n-s)/c+4;break}l/=6}return t.h=l,t.s=h,t.l=d,t}getRGB(t,e=Jt.workingColorSpace){return Jt.fromWorkingColorSpace(we.copy(this),e),t.r=we.r,t.g=we.g,t.b=we.b,t}getStyle(t=je){Jt.fromWorkingColorSpace(we.copy(this),t);const e=we.r,n=we.g,s=we.b;return t!==je?`color(${t} ${e.toFixed(3)} ${n.toFixed(3)} ${s.toFixed(3)})`:`rgb(${Math.round(e*255)},${Math.round(n*255)},${Math.round(s*255)})`}offsetHSL(t,e,n){return this.getHSL(Tn),this.setHSL(Tn.h+t,Tn.s+e,Tn.l+n)}add(t){return this.r+=t.r,this.g+=t.g,this.b+=t.b,this}addColors(t,e){return this.r=t.r+e.r,this.g=t.g+e.g,this.b=t.b+e.b,this}addScalar(t){return this.r+=t,this.g+=t,this.b+=t,this}sub(t){return this.r=Math.max(0,this.r-t.r),this.g=Math.max(0,this.g-t.g),this.b=Math.max(0,this.b-t.b),this}multiply(t){return this.r*=t.r,this.g*=t.g,this.b*=t.b,this}multiplyScalar(t){return this.r*=t,this.g*=t,this.b*=t,this}lerp(t,e){return this.r+=(t.r-this.r)*e,this.g+=(t.g-this.g)*e,this.b+=(t.b-this.b)*e,this}lerpColors(t,e,n){return this.r=t.r+(e.r-t.r)*n,this.g=t.g+(e.g-t.g)*n,this.b=t.b+(e.b-t.b)*n,this}lerpHSL(t,e){this.getHSL(Tn),t.getHSL(Ms);const n=ts(Tn.h,Ms.h,e),s=ts(Tn.s,Ms.s,e),r=ts(Tn.l,Ms.l,e);return this.setHSL(n,s,r),this}setFromVector3(t){return this.r=t.x,this.g=t.y,this.b=t.z,this}applyMatrix3(t){const e=this.r,n=this.g,s=this.b,r=t.elements;return this.r=r[0]*e+r[3]*n+r[6]*s,this.g=r[1]*e+r[4]*n+r[7]*s,this.b=r[2]*e+r[5]*n+r[8]*s,this}equals(t){return t.r===this.r&&t.g===this.g&&t.b===this.b}fromArray(t,e=0){return this.r=t[e],this.g=t[e+1],this.b=t[e+2],this}toArray(t=[],e=0){return t[e]=this.r,t[e+1]=this.g,t[e+2]=this.b,t}fromBufferAttribute(t,e){return this.r=t.getX(e),this.g=t.getY(e),this.b=t.getZ(e),this}toJSON(){return this.getHex()}*[Symbol.iterator](){yield this.r,yield this.g,yield this.b}}const we=new Pt;Pt.NAMES=Kl;let Yh=0;class Bi extends Ni{constructor(){super(),this.isMaterial=!0,Object.defineProperty(this,"id",{value:Yh++}),this.uuid=Fi(),this.name="",this.type="Material",this.blending=Ei,this.side=hn,this.vertexColors=!1,this.opacity=1,this.transparent=!1,this.alphaHash=!1,this.blendSrc=qr,this.blendDst=Kr,this.blendEquation=qn,this.blendSrcAlpha=null,this.blendDstAlpha=null,this.blendEquationAlpha=null,this.blendColor=new Pt(0,0,0),this.blendAlpha=0,this.depthFunc=Ri,this.depthTest=!0,this.depthWrite=!0,this.stencilWriteMask=255,this.stencilFunc=co,this.stencilRef=0,this.stencilFuncMask=255,this.stencilFail=ni,this.stencilZFail=ni,this.stencilZPass=ni,this.stencilWrite=!1,this.clippingPlanes=null,this.clipIntersection=!1,this.clipShadows=!1,this.shadowSide=null,this.colorWrite=!0,this.precision=null,this.polygonOffset=!1,this.polygonOffsetFactor=0,this.polygonOffsetUnits=0,this.dithering=!1,this.alphaToCoverage=!1,this.premultipliedAlpha=!1,this.forceSinglePass=!1,this.visible=!0,this.toneMapped=!0,this.userData={},this.version=0,this._alphaTest=0}get alphaTest(){return this._alphaTest}set alphaTest(t){this._alphaTest>0!=t>0&&this.version++,this._alphaTest=t}onBeforeRender(){}onBeforeCompile(){}customProgramCacheKey(){return this.onBeforeCompile.toString()}setValues(t){if(t!==void 0)for(const e in t){const n=t[e];if(n===void 0){console.warn(`THREE.Material: parameter '${e}' has value of undefined.`);continue}const s=this[e];if(s===void 0){console.warn(`THREE.Material: '${e}' is not a property of THREE.${this.type}.`);continue}s&&s.isColor?s.set(n):s&&s.isVector3&&n&&n.isVector3?s.copy(n):this[e]=n}}toJSON(t){const e=t===void 0||typeof t=="string";e&&(t={textures:{},images:{}});const n={metadata:{version:4.6,type:"Material",generator:"Material.toJSON"}};n.uuid=this.uuid,n.type=this.type,this.name!==""&&(n.name=this.name),this.color&&this.color.isColor&&(n.color=this.color.getHex()),this.roughness!==void 0&&(n.roughness=this.roughness),this.metalness!==void 0&&(n.metalness=this.metalness),this.sheen!==void 0&&(n.sheen=this.sheen),this.sheenColor&&this.sheenColor.isColor&&(n.sheenColor=this.sheenColor.getHex()),this.sheenRoughness!==void 0&&(n.sheenRoughness=this.sheenRoughness),this.emissive&&this.emissive.isColor&&(n.emissive=this.emissive.getHex()),this.emissiveIntensity!==void 0&&this.emissiveIntensity!==1&&(n.emissiveIntensity=this.emissiveIntensity),this.specular&&this.specular.isColor&&(n.specular=this.specular.getHex()),this.specularIntensity!==void 0&&(n.specularIntensity=this.specularIntensity),this.specularColor&&this.specularColor.isColor&&(n.specularColor=this.specularColor.getHex()),this.shininess!==void 0&&(n.shininess=this.shininess),this.clearcoat!==void 0&&(n.clearcoat=this.clearcoat),this.clearcoatRoughness!==void 0&&(n.clearcoatRoughness=this.clearcoatRoughness),this.clearcoatMap&&this.clearcoatMap.isTexture&&(n.clearcoatMap=this.clearcoatMap.toJSON(t).uuid),this.clearcoatRoughnessMap&&this.clearcoatRoughnessMap.isTexture&&(n.clearcoatRoughnessMap=this.clearcoatRoughnessMap.toJSON(t).uuid),this.clearcoatNormalMap&&this.clearcoatNormalMap.isTexture&&(n.clearcoatNormalMap=this.clearcoatNormalMap.toJSON(t).uuid,n.clearcoatNormalScale=this.clearcoatNormalScale.toArray()),this.dispersion!==void 0&&(n.dispersion=this.dispersion),this.iridescence!==void 0&&(n.iridescence=this.iridescence),this.iridescenceIOR!==void 0&&(n.iridescenceIOR=this.iridescenceIOR),this.iridescenceThicknessRange!==void 0&&(n.iridescenceThicknessRange=this.iridescenceThicknessRange),this.iridescenceMap&&this.iridescenceMap.isTexture&&(n.iridescenceMap=this.iridescenceMap.toJSON(t).uuid),this.iridescenceThicknessMap&&this.iridescenceThicknessMap.isTexture&&(n.iridescenceThicknessMap=this.iridescenceThicknessMap.toJSON(t).uuid),this.anisotropy!==void 0&&(n.anisotropy=this.anisotropy),this.anisotropyRotation!==void 0&&(n.anisotropyRotation=this.anisotropyRotation),this.anisotropyMap&&this.anisotropyMap.isTexture&&(n.anisotropyMap=this.anisotropyMap.toJSON(t).uuid),this.map&&this.map.isTexture&&(n.map=this.map.toJSON(t).uuid),this.matcap&&this.matcap.isTexture&&(n.matcap=this.matcap.toJSON(t).uuid),this.alphaMap&&this.alphaMap.isTexture&&(n.alphaMap=this.alphaMap.toJSON(t).uuid),this.lightMap&&this.lightMap.isTexture&&(n.lightMap=this.lightMap.toJSON(t).uuid,n.lightMapIntensity=this.lightMapIntensity),this.aoMap&&this.aoMap.isTexture&&(n.aoMap=this.aoMap.toJSON(t).uuid,n.aoMapIntensity=this.aoMapIntensity),this.bumpMap&&this.bumpMap.isTexture&&(n.bumpMap=this.bumpMap.toJSON(t).uuid,n.bumpScale=this.bumpScale),this.normalMap&&this.normalMap.isTexture&&(n.normalMap=this.normalMap.toJSON(t).uuid,n.normalMapType=this.normalMapType,n.normalScale=this.normalScale.toArray()),this.displacementMap&&this.displacementMap.isTexture&&(n.displacementMap=this.displacementMap.toJSON(t).uuid,n.displacementScale=this.displacementScale,n.displacementBias=this.displacementBias),this.roughnessMap&&this.roughnessMap.isTexture&&(n.roughnessMap=this.roughnessMap.toJSON(t).uuid),this.metalnessMap&&this.metalnessMap.isTexture&&(n.metalnessMap=this.metalnessMap.toJSON(t).uuid),this.emissiveMap&&this.emissiveMap.isTexture&&(n.emissiveMap=this.emissiveMap.toJSON(t).uuid),this.specularMap&&this.specularMap.isTexture&&(n.specularMap=this.specularMap.toJSON(t).uuid),this.specularIntensityMap&&this.specularIntensityMap.isTexture&&(n.specularIntensityMap=this.specularIntensityMap.toJSON(t).uuid),this.specularColorMap&&this.specularColorMap.isTexture&&(n.specularColorMap=this.specularColorMap.toJSON(t).uuid),this.envMap&&this.envMap.isTexture&&(n.envMap=this.envMap.toJSON(t).uuid,this.combine!==void 0&&(n.combine=this.combine)),this.envMapRotation!==void 0&&(n.envMapRotation=this.envMapRotation.toArray()),this.envMapIntensity!==void 0&&(n.envMapIntensity=this.envMapIntensity),this.reflectivity!==void 0&&(n.reflectivity=this.reflectivity),this.refractionRatio!==void 0&&(n.refractionRatio=this.refractionRatio),this.gradientMap&&this.gradientMap.isTexture&&(n.gradientMap=this.gradientMap.toJSON(t).uuid),this.transmission!==void 0&&(n.transmission=this.transmission),this.transmissionMap&&this.transmissionMap.isTexture&&(n.transmissionMap=this.transmissionMap.toJSON(t).uuid),this.thickness!==void 0&&(n.thickness=this.thickness),this.thicknessMap&&this.thicknessMap.isTexture&&(n.thicknessMap=this.thicknessMap.toJSON(t).uuid),this.attenuationDistance!==void 0&&this.attenuationDistance!==1/0&&(n.attenuationDistance=this.attenuationDistance),this.attenuationColor!==void 0&&(n.attenuationColor=this.attenuationColor.getHex()),this.size!==void 0&&(n.size=this.size),this.shadowSide!==null&&(n.shadowSide=this.shadowSide),this.sizeAttenuation!==void 0&&(n.sizeAttenuation=this.sizeAttenuation),this.blending!==Ei&&(n.blending=this.blending),this.side!==hn&&(n.side=this.side),this.vertexColors===!0&&(n.vertexColors=!0),this.opacity<1&&(n.opacity=this.opacity),this.transparent===!0&&(n.transparent=!0),this.blendSrc!==qr&&(n.blendSrc=this.blendSrc),this.blendDst!==Kr&&(n.blendDst=this.blendDst),this.blendEquation!==qn&&(n.blendEquation=this.blendEquation),this.blendSrcAlpha!==null&&(n.blendSrcAlpha=this.blendSrcAlpha),this.blendDstAlpha!==null&&(n.blendDstAlpha=this.blendDstAlpha),this.blendEquationAlpha!==null&&(n.blendEquationAlpha=this.blendEquationAlpha),this.blendColor&&this.blendColor.isColor&&(n.blendColor=this.blendColor.getHex()),this.blendAlpha!==0&&(n.blendAlpha=this.blendAlpha),this.depthFunc!==Ri&&(n.depthFunc=this.depthFunc),this.depthTest===!1&&(n.depthTest=this.depthTest),this.depthWrite===!1&&(n.depthWrite=this.depthWrite),this.colorWrite===!1&&(n.colorWrite=this.colorWrite),this.stencilWriteMask!==255&&(n.stencilWriteMask=this.stencilWriteMask),this.stencilFunc!==co&&(n.stencilFunc=this.stencilFunc),this.stencilRef!==0&&(n.stencilRef=this.stencilRef),this.stencilFuncMask!==255&&(n.stencilFuncMask=this.stencilFuncMask),this.stencilFail!==ni&&(n.stencilFail=this.stencilFail),this.stencilZFail!==ni&&(n.stencilZFail=this.stencilZFail),this.stencilZPass!==ni&&(n.stencilZPass=this.stencilZPass),this.stencilWrite===!0&&(n.stencilWrite=this.stencilWrite),this.rotation!==void 0&&this.rotation!==0&&(n.rotation=this.rotation),this.polygonOffset===!0&&(n.polygonOffset=!0),this.polygonOffsetFactor!==0&&(n.polygonOffsetFactor=this.polygonOffsetFactor),this.polygonOffsetUnits!==0&&(n.polygonOffsetUnits=this.polygonOffsetUnits),this.linewidth!==void 0&&this.linewidth!==1&&(n.linewidth=this.linewidth),this.dashSize!==void 0&&(n.dashSize=this.dashSize),this.gapSize!==void 0&&(n.gapSize=this.gapSize),this.scale!==void 0&&(n.scale=this.scale),this.dithering===!0&&(n.dithering=!0),this.alphaTest>0&&(n.alphaTest=this.alphaTest),this.alphaHash===!0&&(n.alphaHash=!0),this.alphaToCoverage===!0&&(n.alphaToCoverage=!0),this.premultipliedAlpha===!0&&(n.premultipliedAlpha=!0),this.forceSinglePass===!0&&(n.forceSinglePass=!0),this.wireframe===!0&&(n.wireframe=!0),this.wireframeLinewidth>1&&(n.wireframeLinewidth=this.wireframeLinewidth),this.wireframeLinecap!=="round"&&(n.wireframeLinecap=this.wireframeLinecap),this.wireframeLinejoin!=="round"&&(n.wireframeLinejoin=this.wireframeLinejoin),this.flatShading===!0&&(n.flatShading=!0),this.visible===!1&&(n.visible=!1),this.toneMapped===!1&&(n.toneMapped=!1),this.fog===!1&&(n.fog=!1),Object.keys(this.userData).length>0&&(n.userData=this.userData);function s(r){const a=[];for(const o in r){const l=r[o];delete l.metadata,a.push(l)}return a}if(e){const r=s(t.textures),a=s(t.images);r.length>0&&(n.textures=r),a.length>0&&(n.images=a)}return n}clone(){return new this.constructor().copy(this)}copy(t){this.name=t.name,this.blending=t.blending,this.side=t.side,this.vertexColors=t.vertexColors,this.opacity=t.opacity,this.transparent=t.transparent,this.blendSrc=t.blendSrc,this.blendDst=t.blendDst,this.blendEquation=t.blendEquation,this.blendSrcAlpha=t.blendSrcAlpha,this.blendDstAlpha=t.blendDstAlpha,this.blendEquationAlpha=t.blendEquationAlpha,this.blendColor.copy(t.blendColor),this.blendAlpha=t.blendAlpha,this.depthFunc=t.depthFunc,this.depthTest=t.depthTest,this.depthWrite=t.depthWrite,this.stencilWriteMask=t.stencilWriteMask,this.stencilFunc=t.stencilFunc,this.stencilRef=t.stencilRef,this.stencilFuncMask=t.stencilFuncMask,this.stencilFail=t.stencilFail,this.stencilZFail=t.stencilZFail,this.stencilZPass=t.stencilZPass,this.stencilWrite=t.stencilWrite;const e=t.clippingPlanes;let n=null;if(e!==null){const s=e.length;n=new Array(s);for(let r=0;r!==s;++r)n[r]=e[r].clone()}return this.clippingPlanes=n,this.clipIntersection=t.clipIntersection,this.clipShadows=t.clipShadows,this.shadowSide=t.shadowSide,this.colorWrite=t.colorWrite,this.precision=t.precision,this.polygonOffset=t.polygonOffset,this.polygonOffsetFactor=t.polygonOffsetFactor,this.polygonOffsetUnits=t.polygonOffsetUnits,this.dithering=t.dithering,this.alphaTest=t.alphaTest,this.alphaHash=t.alphaHash,this.alphaToCoverage=t.alphaToCoverage,this.premultipliedAlpha=t.premultipliedAlpha,this.forceSinglePass=t.forceSinglePass,this.visible=t.visible,this.toneMapped=t.toneMapped,this.userData=JSON.parse(JSON.stringify(t.userData)),this}dispose(){this.dispatchEvent({type:"dispose"})}set needsUpdate(t){t===!0&&this.version++}onBuild(){console.warn("Material: onBuild() has been removed.")}}class fe extends Bi{constructor(t){super(),this.isMeshBasicMaterial=!0,this.type="MeshBasicMaterial",this.color=new Pt(16777215),this.map=null,this.lightMap=null,this.lightMapIntensity=1,this.aoMap=null,this.aoMapIntensity=1,this.specularMap=null,this.alphaMap=null,this.envMap=null,this.envMapRotation=new on,this.combine=Ll,this.reflectivity=1,this.refractionRatio=.98,this.wireframe=!1,this.wireframeLinewidth=1,this.wireframeLinecap="round",this.wireframeLinejoin="round",this.fog=!0,this.setValues(t)}copy(t){return super.copy(t),this.color.copy(t.color),this.map=t.map,this.lightMap=t.lightMap,this.lightMapIntensity=t.lightMapIntensity,this.aoMap=t.aoMap,this.aoMapIntensity=t.aoMapIntensity,this.specularMap=t.specularMap,this.alphaMap=t.alphaMap,this.envMap=t.envMap,this.envMapRotation.copy(t.envMapRotation),this.combine=t.combine,this.reflectivity=t.reflectivity,this.refractionRatio=t.refractionRatio,this.wireframe=t.wireframe,this.wireframeLinewidth=t.wireframeLinewidth,this.wireframeLinecap=t.wireframeLinecap,this.wireframeLinejoin=t.wireframeLinejoin,this.fog=t.fog,this}}const ue=new R,ys=new Ht;class Xe{constructor(t,e,n=!1){if(Array.isArray(t))throw new TypeError("THREE.BufferAttribute: array should be a Typed Array.");this.isBufferAttribute=!0,this.name="",this.array=t,this.itemSize=e,this.count=t!==void 0?t.length/e:0,this.normalized=n,this.usage=ho,this.updateRanges=[],this.gpuType=cn,this.version=0}onUploadCallback(){}set needsUpdate(t){t===!0&&this.version++}setUsage(t){return this.usage=t,this}addUpdateRange(t,e){this.updateRanges.push({start:t,count:e})}clearUpdateRanges(){this.updateRanges.length=0}copy(t){return this.name=t.name,this.array=new t.array.constructor(t.array),this.itemSize=t.itemSize,this.count=t.count,this.normalized=t.normalized,this.usage=t.usage,this.gpuType=t.gpuType,this}copyAt(t,e,n){t*=this.itemSize,n*=e.itemSize;for(let s=0,r=this.itemSize;s<r;s++)this.array[t+s]=e.array[n+s];return this}copyArray(t){return this.array.set(t),this}applyMatrix3(t){if(this.itemSize===2)for(let e=0,n=this.count;e<n;e++)ys.fromBufferAttribute(this,e),ys.applyMatrix3(t),this.setXY(e,ys.x,ys.y);else if(this.itemSize===3)for(let e=0,n=this.count;e<n;e++)ue.fromBufferAttribute(this,e),ue.applyMatrix3(t),this.setXYZ(e,ue.x,ue.y,ue.z);return this}applyMatrix4(t){for(let e=0,n=this.count;e<n;e++)ue.fromBufferAttribute(this,e),ue.applyMatrix4(t),this.setXYZ(e,ue.x,ue.y,ue.z);return this}applyNormalMatrix(t){for(let e=0,n=this.count;e<n;e++)ue.fromBufferAttribute(this,e),ue.applyNormalMatrix(t),this.setXYZ(e,ue.x,ue.y,ue.z);return this}transformDirection(t){for(let e=0,n=this.count;e<n;e++)ue.fromBufferAttribute(this,e),ue.transformDirection(t),this.setXYZ(e,ue.x,ue.y,ue.z);return this}set(t,e=0){return this.array.set(t,e),this}getComponent(t,e){let n=this.array[t*this.itemSize+e];return this.normalized&&(n=vi(n,this.array)),n}setComponent(t,e,n){return this.normalized&&(n=Re(n,this.array)),this.array[t*this.itemSize+e]=n,this}getX(t){let e=this.array[t*this.itemSize];return this.normalized&&(e=vi(e,this.array)),e}setX(t,e){return this.normalized&&(e=Re(e,this.array)),this.array[t*this.itemSize]=e,this}getY(t){let e=this.array[t*this.itemSize+1];return this.normalized&&(e=vi(e,this.array)),e}setY(t,e){return this.normalized&&(e=Re(e,this.array)),this.array[t*this.itemSize+1]=e,this}getZ(t){let e=this.array[t*this.itemSize+2];return this.normalized&&(e=vi(e,this.array)),e}setZ(t,e){return this.normalized&&(e=Re(e,this.array)),this.array[t*this.itemSize+2]=e,this}getW(t){let e=this.array[t*this.itemSize+3];return this.normalized&&(e=vi(e,this.array)),e}setW(t,e){return this.normalized&&(e=Re(e,this.array)),this.array[t*this.itemSize+3]=e,this}setXY(t,e,n){return t*=this.itemSize,this.normalized&&(e=Re(e,this.array),n=Re(n,this.array)),this.array[t+0]=e,this.array[t+1]=n,this}setXYZ(t,e,n,s){return t*=this.itemSize,this.normalized&&(e=Re(e,this.array),n=Re(n,this.array),s=Re(s,this.array)),this.array[t+0]=e,this.array[t+1]=n,this.array[t+2]=s,this}setXYZW(t,e,n,s,r){return t*=this.itemSize,this.normalized&&(e=Re(e,this.array),n=Re(n,this.array),s=Re(s,this.array),r=Re(r,this.array)),this.array[t+0]=e,this.array[t+1]=n,this.array[t+2]=s,this.array[t+3]=r,this}onUpload(t){return this.onUploadCallback=t,this}clone(){return new this.constructor(this.array,this.itemSize).copy(this)}toJSON(){const t={itemSize:this.itemSize,type:this.array.constructor.name,array:Array.from(this.array),normalized:this.normalized};return this.name!==""&&(t.name=this.name),this.usage!==ho&&(t.usage=this.usage),t}}class jl extends Xe{constructor(t,e,n){super(new Uint16Array(t),e,n)}}class Zl extends Xe{constructor(t,e,n){super(new Uint32Array(t),e,n)}}class le extends Xe{constructor(t,e,n){super(new Float32Array(t),e,n)}}let qh=0;const qe=new ee,Lr=new me,di=new R,Be=new Un,Wi=new Un,xe=new R;class Le extends Ni{constructor(){super(),this.isBufferGeometry=!0,Object.defineProperty(this,"id",{value:qh++}),this.uuid=Fi(),this.name="",this.type="BufferGeometry",this.index=null,this.attributes={},this.morphAttributes={},this.morphTargetsRelative=!1,this.groups=[],this.boundingBox=null,this.boundingSphere=null,this.drawRange={start:0,count:1/0},this.userData={}}getIndex(){return this.index}setIndex(t){return Array.isArray(t)?this.index=new(Xl(t)?Zl:jl)(t,1):this.index=t,this}getAttribute(t){return this.attributes[t]}setAttribute(t,e){return this.attributes[t]=e,this}deleteAttribute(t){return delete this.attributes[t],this}hasAttribute(t){return this.attributes[t]!==void 0}addGroup(t,e,n=0){this.groups.push({start:t,count:e,materialIndex:n})}clearGroups(){this.groups=[]}setDrawRange(t,e){this.drawRange.start=t,this.drawRange.count=e}applyMatrix4(t){const e=this.attributes.position;e!==void 0&&(e.applyMatrix4(t),e.needsUpdate=!0);const n=this.attributes.normal;if(n!==void 0){const r=new Ot().getNormalMatrix(t);n.applyNormalMatrix(r),n.needsUpdate=!0}const s=this.attributes.tangent;return s!==void 0&&(s.transformDirection(t),s.needsUpdate=!0),this.boundingBox!==null&&this.computeBoundingBox(),this.boundingSphere!==null&&this.computeBoundingSphere(),this}applyQuaternion(t){return qe.makeRotationFromQuaternion(t),this.applyMatrix4(qe),this}rotateX(t){return qe.makeRotationX(t),this.applyMatrix4(qe),this}rotateY(t){return qe.makeRotationY(t),this.applyMatrix4(qe),this}rotateZ(t){return qe.makeRotationZ(t),this.applyMatrix4(qe),this}translate(t,e,n){return qe.makeTranslation(t,e,n),this.applyMatrix4(qe),this}scale(t,e,n){return qe.makeScale(t,e,n),this.applyMatrix4(qe),this}lookAt(t){return Lr.lookAt(t),Lr.updateMatrix(),this.applyMatrix4(Lr.matrix),this}center(){return this.computeBoundingBox(),this.boundingBox.getCenter(di).negate(),this.translate(di.x,di.y,di.z),this}setFromPoints(t){const e=[];for(let n=0,s=t.length;n<s;n++){const r=t[n];e.push(r.x,r.y,r.z||0)}return this.setAttribute("position",new le(e,3)),this}computeBoundingBox(){this.boundingBox===null&&(this.boundingBox=new Un);const t=this.attributes.position,e=this.morphAttributes.position;if(t&&t.isGLBufferAttribute){console.error("THREE.BufferGeometry.computeBoundingBox(): GLBufferAttribute requires a manual bounding box.",this),this.boundingBox.set(new R(-1/0,-1/0,-1/0),new R(1/0,1/0,1/0));return}if(t!==void 0){if(this.boundingBox.setFromBufferAttribute(t),e)for(let n=0,s=e.length;n<s;n++){const r=e[n];Be.setFromBufferAttribute(r),this.morphTargetsRelative?(xe.addVectors(this.boundingBox.min,Be.min),this.boundingBox.expandByPoint(xe),xe.addVectors(this.boundingBox.max,Be.max),this.boundingBox.expandByPoint(xe)):(this.boundingBox.expandByPoint(Be.min),this.boundingBox.expandByPoint(Be.max))}}else this.boundingBox.makeEmpty();(isNaN(this.boundingBox.min.x)||isNaN(this.boundingBox.min.y)||isNaN(this.boundingBox.min.z))&&console.error('THREE.BufferGeometry.computeBoundingBox(): Computed min/max have NaN values. The "position" attribute is likely to have NaN values.',this)}computeBoundingSphere(){this.boundingSphere===null&&(this.boundingSphere=new Oi);const t=this.attributes.position,e=this.morphAttributes.position;if(t&&t.isGLBufferAttribute){console.error("THREE.BufferGeometry.computeBoundingSphere(): GLBufferAttribute requires a manual bounding sphere.",this),this.boundingSphere.set(new R,1/0);return}if(t){const n=this.boundingSphere.center;if(Be.setFromBufferAttribute(t),e)for(let r=0,a=e.length;r<a;r++){const o=e[r];Wi.setFromBufferAttribute(o),this.morphTargetsRelative?(xe.addVectors(Be.min,Wi.min),Be.expandByPoint(xe),xe.addVectors(Be.max,Wi.max),Be.expandByPoint(xe)):(Be.expandByPoint(Wi.min),Be.expandByPoint(Wi.max))}Be.getCenter(n);let s=0;for(let r=0,a=t.count;r<a;r++)xe.fromBufferAttribute(t,r),s=Math.max(s,n.distanceToSquared(xe));if(e)for(let r=0,a=e.length;r<a;r++){const o=e[r],l=this.morphTargetsRelative;for(let h=0,d=o.count;h<d;h++)xe.fromBufferAttribute(o,h),l&&(di.fromBufferAttribute(t,h),xe.add(di)),s=Math.max(s,n.distanceToSquared(xe))}this.boundingSphere.radius=Math.sqrt(s),isNaN(this.boundingSphere.radius)&&console.error('THREE.BufferGeometry.computeBoundingSphere(): Computed radius is NaN. The "position" attribute is likely to have NaN values.',this)}}computeTangents(){const t=this.index,e=this.attributes;if(t===null||e.position===void 0||e.normal===void 0||e.uv===void 0){console.error("THREE.BufferGeometry: .computeTangents() failed. Missing required attributes (index, position, normal or uv)");return}const n=e.position,s=e.normal,r=e.uv;this.hasAttribute("tangent")===!1&&this.setAttribute("tangent",new Xe(new Float32Array(4*n.count),4));const a=this.getAttribute("tangent"),o=[],l=[];for(let L=0;L<n.count;L++)o[L]=new R,l[L]=new R;const h=new R,d=new R,c=new R,u=new Ht,f=new Ht,g=new Ht,v=new R,m=new R;function p(L,q,x){h.fromBufferAttribute(n,L),d.fromBufferAttribute(n,q),c.fromBufferAttribute(n,x),u.fromBufferAttribute(r,L),f.fromBufferAttribute(r,q),g.fromBufferAttribute(r,x),d.sub(h),c.sub(h),f.sub(u),g.sub(u);const E=1/(f.x*g.y-g.x*f.y);isFinite(E)&&(v.copy(d).multiplyScalar(g.y).addScaledVector(c,-f.y).multiplyScalar(E),m.copy(c).multiplyScalar(f.x).addScaledVector(d,-g.x).multiplyScalar(E),o[L].add(v),o[q].add(v),o[x].add(v),l[L].add(m),l[q].add(m),l[x].add(m))}let y=this.groups;y.length===0&&(y=[{start:0,count:t.count}]);for(let L=0,q=y.length;L<q;++L){const x=y[L],E=x.start,z=x.count;for(let V=E,K=E+z;V<K;V+=3)p(t.getX(V+0),t.getX(V+1),t.getX(V+2))}const _=new R,S=new R,P=new R,T=new R;function A(L){P.fromBufferAttribute(s,L),T.copy(P);const q=o[L];_.copy(q),_.sub(P.multiplyScalar(P.dot(q))).normalize(),S.crossVectors(T,q);const E=S.dot(l[L])<0?-1:1;a.setXYZW(L,_.x,_.y,_.z,E)}for(let L=0,q=y.length;L<q;++L){const x=y[L],E=x.start,z=x.count;for(let V=E,K=E+z;V<K;V+=3)A(t.getX(V+0)),A(t.getX(V+1)),A(t.getX(V+2))}}computeVertexNormals(){const t=this.index,e=this.getAttribute("position");if(e!==void 0){let n=this.getAttribute("normal");if(n===void 0)n=new Xe(new Float32Array(e.count*3),3),this.setAttribute("normal",n);else for(let u=0,f=n.count;u<f;u++)n.setXYZ(u,0,0,0);const s=new R,r=new R,a=new R,o=new R,l=new R,h=new R,d=new R,c=new R;if(t)for(let u=0,f=t.count;u<f;u+=3){const g=t.getX(u+0),v=t.getX(u+1),m=t.getX(u+2);s.fromBufferAttribute(e,g),r.fromBufferAttribute(e,v),a.fromBufferAttribute(e,m),d.subVectors(a,r),c.subVectors(s,r),d.cross(c),o.fromBufferAttribute(n,g),l.fromBufferAttribute(n,v),h.fromBufferAttribute(n,m),o.add(d),l.add(d),h.add(d),n.setXYZ(g,o.x,o.y,o.z),n.setXYZ(v,l.x,l.y,l.z),n.setXYZ(m,h.x,h.y,h.z)}else for(let u=0,f=e.count;u<f;u+=3)s.fromBufferAttribute(e,u+0),r.fromBufferAttribute(e,u+1),a.fromBufferAttribute(e,u+2),d.subVectors(a,r),c.subVectors(s,r),d.cross(c),n.setXYZ(u+0,d.x,d.y,d.z),n.setXYZ(u+1,d.x,d.y,d.z),n.setXYZ(u+2,d.x,d.y,d.z);this.normalizeNormals(),n.needsUpdate=!0}}normalizeNormals(){const t=this.attributes.normal;for(let e=0,n=t.count;e<n;e++)xe.fromBufferAttribute(t,e),xe.normalize(),t.setXYZ(e,xe.x,xe.y,xe.z)}toNonIndexed(){function t(o,l){const h=o.array,d=o.itemSize,c=o.normalized,u=new h.constructor(l.length*d);let f=0,g=0;for(let v=0,m=l.length;v<m;v++){o.isInterleavedBufferAttribute?f=l[v]*o.data.stride+o.offset:f=l[v]*d;for(let p=0;p<d;p++)u[g++]=h[f++]}return new Xe(u,d,c)}if(this.index===null)return console.warn("THREE.BufferGeometry.toNonIndexed(): BufferGeometry is already non-indexed."),this;const e=new Le,n=this.index.array,s=this.attributes;for(const o in s){const l=s[o],h=t(l,n);e.setAttribute(o,h)}const r=this.morphAttributes;for(const o in r){const l=[],h=r[o];for(let d=0,c=h.length;d<c;d++){const u=h[d],f=t(u,n);l.push(f)}e.morphAttributes[o]=l}e.morphTargetsRelative=this.morphTargetsRelative;const a=this.groups;for(let o=0,l=a.length;o<l;o++){const h=a[o];e.addGroup(h.start,h.count,h.materialIndex)}return e}toJSON(){const t={metadata:{version:4.6,type:"BufferGeometry",generator:"BufferGeometry.toJSON"}};if(t.uuid=this.uuid,t.type=this.type,this.name!==""&&(t.name=this.name),Object.keys(this.userData).length>0&&(t.userData=this.userData),this.parameters!==void 0){const l=this.parameters;for(const h in l)l[h]!==void 0&&(t[h]=l[h]);return t}t.data={attributes:{}};const e=this.index;e!==null&&(t.data.index={type:e.array.constructor.name,array:Array.prototype.slice.call(e.array)});const n=this.attributes;for(const l in n){const h=n[l];t.data.attributes[l]=h.toJSON(t.data)}const s={};let r=!1;for(const l in this.morphAttributes){const h=this.morphAttributes[l],d=[];for(let c=0,u=h.length;c<u;c++){const f=h[c];d.push(f.toJSON(t.data))}d.length>0&&(s[l]=d,r=!0)}r&&(t.data.morphAttributes=s,t.data.morphTargetsRelative=this.morphTargetsRelative);const a=this.groups;a.length>0&&(t.data.groups=JSON.parse(JSON.stringify(a)));const o=this.boundingSphere;return o!==null&&(t.data.boundingSphere={center:o.center.toArray(),radius:o.radius}),t}clone(){return new this.constructor().copy(this)}copy(t){this.index=null,this.attributes={},this.morphAttributes={},this.groups=[],this.boundingBox=null,this.boundingSphere=null;const e={};this.name=t.name;const n=t.index;n!==null&&this.setIndex(n.clone(e));const s=t.attributes;for(const h in s){const d=s[h];this.setAttribute(h,d.clone(e))}const r=t.morphAttributes;for(const h in r){const d=[],c=r[h];for(let u=0,f=c.length;u<f;u++)d.push(c[u].clone(e));this.morphAttributes[h]=d}this.morphTargetsRelative=t.morphTargetsRelative;const a=t.groups;for(let h=0,d=a.length;h<d;h++){const c=a[h];this.addGroup(c.start,c.count,c.materialIndex)}const o=t.boundingBox;o!==null&&(this.boundingBox=o.clone());const l=t.boundingSphere;return l!==null&&(this.boundingSphere=l.clone()),this.drawRange.start=t.drawRange.start,this.drawRange.count=t.drawRange.count,this.userData=t.userData,this}dispose(){this.dispatchEvent({type:"dispose"})}}const To=new ee,Bn=new Xa,Ss=new Oi,Ao=new R,ws=new R,Es=new R,bs=new R,Dr=new R,Ts=new R,Ro=new R,As=new R;class Ct extends me{constructor(t=new Le,e=new fe){super(),this.isMesh=!0,this.type="Mesh",this.geometry=t,this.material=e,this.updateMorphTargets()}copy(t,e){return super.copy(t,e),t.morphTargetInfluences!==void 0&&(this.morphTargetInfluences=t.morphTargetInfluences.slice()),t.morphTargetDictionary!==void 0&&(this.morphTargetDictionary=Object.assign({},t.morphTargetDictionary)),this.material=Array.isArray(t.material)?t.material.slice():t.material,this.geometry=t.geometry,this}updateMorphTargets(){const e=this.geometry.morphAttributes,n=Object.keys(e);if(n.length>0){const s=e[n[0]];if(s!==void 0){this.morphTargetInfluences=[],this.morphTargetDictionary={};for(let r=0,a=s.length;r<a;r++){const o=s[r].name||String(r);this.morphTargetInfluences.push(0),this.morphTargetDictionary[o]=r}}}}getVertexPosition(t,e){const n=this.geometry,s=n.attributes.position,r=n.morphAttributes.position,a=n.morphTargetsRelative;e.fromBufferAttribute(s,t);const o=this.morphTargetInfluences;if(r&&o){Ts.set(0,0,0);for(let l=0,h=r.length;l<h;l++){const d=o[l],c=r[l];d!==0&&(Dr.fromBufferAttribute(c,t),a?Ts.addScaledVector(Dr,d):Ts.addScaledVector(Dr.sub(e),d))}e.add(Ts)}return e}raycast(t,e){const n=this.geometry,s=this.material,r=this.matrixWorld;s!==void 0&&(n.boundingSphere===null&&n.computeBoundingSphere(),Ss.copy(n.boundingSphere),Ss.applyMatrix4(r),Bn.copy(t.ray).recast(t.near),!(Ss.containsPoint(Bn.origin)===!1&&(Bn.intersectSphere(Ss,Ao)===null||Bn.origin.distanceToSquared(Ao)>(t.far-t.near)**2))&&(To.copy(r).invert(),Bn.copy(t.ray).applyMatrix4(To),!(n.boundingBox!==null&&Bn.intersectsBox(n.boundingBox)===!1)&&this._computeIntersections(t,e,Bn)))}_computeIntersections(t,e,n){let s;const r=this.geometry,a=this.material,o=r.index,l=r.attributes.position,h=r.attributes.uv,d=r.attributes.uv1,c=r.attributes.normal,u=r.groups,f=r.drawRange;if(o!==null)if(Array.isArray(a))for(let g=0,v=u.length;g<v;g++){const m=u[g],p=a[m.materialIndex],y=Math.max(m.start,f.start),_=Math.min(o.count,Math.min(m.start+m.count,f.start+f.count));for(let S=y,P=_;S<P;S+=3){const T=o.getX(S),A=o.getX(S+1),L=o.getX(S+2);s=Rs(this,p,t,n,h,d,c,T,A,L),s&&(s.faceIndex=Math.floor(S/3),s.face.materialIndex=m.materialIndex,e.push(s))}}else{const g=Math.max(0,f.start),v=Math.min(o.count,f.start+f.count);for(let m=g,p=v;m<p;m+=3){const y=o.getX(m),_=o.getX(m+1),S=o.getX(m+2);s=Rs(this,a,t,n,h,d,c,y,_,S),s&&(s.faceIndex=Math.floor(m/3),e.push(s))}}else if(l!==void 0)if(Array.isArray(a))for(let g=0,v=u.length;g<v;g++){const m=u[g],p=a[m.materialIndex],y=Math.max(m.start,f.start),_=Math.min(l.count,Math.min(m.start+m.count,f.start+f.count));for(let S=y,P=_;S<P;S+=3){const T=S,A=S+1,L=S+2;s=Rs(this,p,t,n,h,d,c,T,A,L),s&&(s.faceIndex=Math.floor(S/3),s.face.materialIndex=m.materialIndex,e.push(s))}}else{const g=Math.max(0,f.start),v=Math.min(l.count,f.start+f.count);for(let m=g,p=v;m<p;m+=3){const y=m,_=m+1,S=m+2;s=Rs(this,a,t,n,h,d,c,y,_,S),s&&(s.faceIndex=Math.floor(m/3),e.push(s))}}}}function Kh(i,t,e,n,s,r,a,o){let l;if(t.side===Pe?l=n.intersectTriangle(a,r,s,!0,o):l=n.intersectTriangle(s,r,a,t.side===hn,o),l===null)return null;As.copy(o),As.applyMatrix4(i.matrixWorld);const h=e.ray.origin.distanceTo(As);return h<e.near||h>e.far?null:{distance:h,point:As.clone(),object:i}}function Rs(i,t,e,n,s,r,a,o,l,h){i.getVertexPosition(o,ws),i.getVertexPosition(l,Es),i.getVertexPosition(h,bs);const d=Kh(i,t,e,n,ws,Es,bs,Ro);if(d){const c=new R;nn.getBarycoord(Ro,ws,Es,bs,c),s&&(d.uv=nn.getInterpolatedAttribute(s,o,l,h,c,new Ht)),r&&(d.uv1=nn.getInterpolatedAttribute(r,o,l,h,c,new Ht)),a&&(d.normal=nn.getInterpolatedAttribute(a,o,l,h,c,new R),d.normal.dot(n.direction)>0&&d.normal.multiplyScalar(-1));const u={a:o,b:l,c:h,normal:new R,materialIndex:0};nn.getNormal(ws,Es,bs,u.normal),d.face=u,d.barycoord=c}return d}class Te extends Le{constructor(t=1,e=1,n=1,s=1,r=1,a=1){super(),this.type="BoxGeometry",this.parameters={width:t,height:e,depth:n,widthSegments:s,heightSegments:r,depthSegments:a};const o=this;s=Math.floor(s),r=Math.floor(r),a=Math.floor(a);const l=[],h=[],d=[],c=[];let u=0,f=0;g("z","y","x",-1,-1,n,e,t,a,r,0),g("z","y","x",1,-1,n,e,-t,a,r,1),g("x","z","y",1,1,t,n,e,s,a,2),g("x","z","y",1,-1,t,n,-e,s,a,3),g("x","y","z",1,-1,t,e,n,s,r,4),g("x","y","z",-1,-1,t,e,-n,s,r,5),this.setIndex(l),this.setAttribute("position",new le(h,3)),this.setAttribute("normal",new le(d,3)),this.setAttribute("uv",new le(c,2));function g(v,m,p,y,_,S,P,T,A,L,q){const x=S/A,E=P/L,z=S/2,V=P/2,K=T/2,G=A+1,I=L+1;let F=0,O=0;const Q=new R;for(let nt=0;nt<I;nt++){const rt=nt*E-V;for(let ht=0;ht<G;ht++){const ot=ht*x-z;Q[v]=ot*y,Q[m]=rt*_,Q[p]=K,h.push(Q.x,Q.y,Q.z),Q[v]=0,Q[m]=0,Q[p]=T>0?1:-1,d.push(Q.x,Q.y,Q.z),c.push(ht/A),c.push(1-nt/L),F+=1}}for(let nt=0;nt<L;nt++)for(let rt=0;rt<A;rt++){const ht=u+rt+G*nt,ot=u+rt+G*(nt+1),W=u+(rt+1)+G*(nt+1),J=u+(rt+1)+G*nt;l.push(ht,ot,J),l.push(ot,W,J),O+=6}o.addGroup(f,O,q),f+=O,u+=F}}copy(t){return super.copy(t),this.parameters=Object.assign({},t.parameters),this}static fromJSON(t){return new Te(t.width,t.height,t.depth,t.widthSegments,t.heightSegments,t.depthSegments)}}function Ii(i){const t={};for(const e in i){t[e]={};for(const n in i[e]){const s=i[e][n];s&&(s.isColor||s.isMatrix3||s.isMatrix4||s.isVector2||s.isVector3||s.isVector4||s.isTexture||s.isQuaternion)?s.isRenderTargetTexture?(console.warn("UniformsUtils: Textures of render targets cannot be cloned via cloneUniforms() or mergeUniforms()."),t[e][n]=null):t[e][n]=s.clone():Array.isArray(s)?t[e][n]=s.slice():t[e][n]=s}}return t}function Ce(i){const t={};for(let e=0;e<i.length;e++){const n=Ii(i[e]);for(const s in n)t[s]=n[s]}return t}function jh(i){const t=[];for(let e=0;e<i.length;e++)t.push(i[e].clone());return t}function $l(i){const t=i.getRenderTarget();return t===null?i.outputColorSpace:t.isXRRenderTarget===!0?t.texture.colorSpace:Jt.workingColorSpace}const Zh={clone:Ii,merge:Ce};var $h=`void main() {
	gl_Position = projectionMatrix * modelViewMatrix * vec4( position, 1.0 );
}`,Jh=`void main() {
	gl_FragColor = vec4( 1.0, 0.0, 0.0, 1.0 );
}`;class an extends Bi{constructor(t){super(),this.isShaderMaterial=!0,this.type="ShaderMaterial",this.defines={},this.uniforms={},this.uniformsGroups=[],this.vertexShader=$h,this.fragmentShader=Jh,this.linewidth=1,this.wireframe=!1,this.wireframeLinewidth=1,this.fog=!1,this.lights=!1,this.clipping=!1,this.forceSinglePass=!0,this.extensions={clipCullDistance:!1,multiDraw:!1},this.defaultAttributeValues={color:[1,1,1],uv:[0,0],uv1:[0,0]},this.index0AttributeName=void 0,this.uniformsNeedUpdate=!1,this.glslVersion=null,t!==void 0&&this.setValues(t)}copy(t){return super.copy(t),this.fragmentShader=t.fragmentShader,this.vertexShader=t.vertexShader,this.uniforms=Ii(t.uniforms),this.uniformsGroups=jh(t.uniformsGroups),this.defines=Object.assign({},t.defines),this.wireframe=t.wireframe,this.wireframeLinewidth=t.wireframeLinewidth,this.fog=t.fog,this.lights=t.lights,this.clipping=t.clipping,this.extensions=Object.assign({},t.extensions),this.glslVersion=t.glslVersion,this}toJSON(t){const e=super.toJSON(t);e.glslVersion=this.glslVersion,e.uniforms={};for(const s in this.uniforms){const a=this.uniforms[s].value;a&&a.isTexture?e.uniforms[s]={type:"t",value:a.toJSON(t).uuid}:a&&a.isColor?e.uniforms[s]={type:"c",value:a.getHex()}:a&&a.isVector2?e.uniforms[s]={type:"v2",value:a.toArray()}:a&&a.isVector3?e.uniforms[s]={type:"v3",value:a.toArray()}:a&&a.isVector4?e.uniforms[s]={type:"v4",value:a.toArray()}:a&&a.isMatrix3?e.uniforms[s]={type:"m3",value:a.toArray()}:a&&a.isMatrix4?e.uniforms[s]={type:"m4",value:a.toArray()}:e.uniforms[s]={value:a}}Object.keys(this.defines).length>0&&(e.defines=this.defines),e.vertexShader=this.vertexShader,e.fragmentShader=this.fragmentShader,e.lights=this.lights,e.clipping=this.clipping;const n={};for(const s in this.extensions)this.extensions[s]===!0&&(n[s]=!0);return Object.keys(n).length>0&&(e.extensions=n),e}}class Jl extends me{constructor(){super(),this.isCamera=!0,this.type="Camera",this.matrixWorldInverse=new ee,this.projectionMatrix=new ee,this.projectionMatrixInverse=new ee,this.coordinateSystem=vn}copy(t,e){return super.copy(t,e),this.matrixWorldInverse.copy(t.matrixWorldInverse),this.projectionMatrix.copy(t.projectionMatrix),this.projectionMatrixInverse.copy(t.projectionMatrixInverse),this.coordinateSystem=t.coordinateSystem,this}getWorldDirection(t){return super.getWorldDirection(t).negate()}updateMatrixWorld(t){super.updateMatrixWorld(t),this.matrixWorldInverse.copy(this.matrixWorld).invert()}updateWorldMatrix(t,e){super.updateWorldMatrix(t,e),this.matrixWorldInverse.copy(this.matrixWorld).invert()}clone(){return new this.constructor().copy(this)}}const An=new R,Co=new Ht,Po=new Ht;class Ve extends Jl{constructor(t=50,e=1,n=.1,s=2e3){super(),this.isPerspectiveCamera=!0,this.type="PerspectiveCamera",this.fov=t,this.zoom=1,this.near=n,this.far=s,this.focus=10,this.aspect=e,this.view=null,this.filmGauge=35,this.filmOffset=0,this.updateProjectionMatrix()}copy(t,e){return super.copy(t,e),this.fov=t.fov,this.zoom=t.zoom,this.near=t.near,this.far=t.far,this.focus=t.focus,this.aspect=t.aspect,this.view=t.view===null?null:Object.assign({},t.view),this.filmGauge=t.filmGauge,this.filmOffset=t.filmOffset,this}setFocalLength(t){const e=.5*this.getFilmHeight()/t;this.fov=as*2*Math.atan(e),this.updateProjectionMatrix()}getFocalLength(){const t=Math.tan(Qi*.5*this.fov);return .5*this.getFilmHeight()/t}getEffectiveFOV(){return as*2*Math.atan(Math.tan(Qi*.5*this.fov)/this.zoom)}getFilmWidth(){return this.filmGauge*Math.min(this.aspect,1)}getFilmHeight(){return this.filmGauge/Math.max(this.aspect,1)}getViewBounds(t,e,n){An.set(-1,-1,.5).applyMatrix4(this.projectionMatrixInverse),e.set(An.x,An.y).multiplyScalar(-t/An.z),An.set(1,1,.5).applyMatrix4(this.projectionMatrixInverse),n.set(An.x,An.y).multiplyScalar(-t/An.z)}getViewSize(t,e){return this.getViewBounds(t,Co,Po),e.subVectors(Po,Co)}setViewOffset(t,e,n,s,r,a){this.aspect=t/e,this.view===null&&(this.view={enabled:!0,fullWidth:1,fullHeight:1,offsetX:0,offsetY:0,width:1,height:1}),this.view.enabled=!0,this.view.fullWidth=t,this.view.fullHeight=e,this.view.offsetX=n,this.view.offsetY=s,this.view.width=r,this.view.height=a,this.updateProjectionMatrix()}clearViewOffset(){this.view!==null&&(this.view.enabled=!1),this.updateProjectionMatrix()}updateProjectionMatrix(){const t=this.near;let e=t*Math.tan(Qi*.5*this.fov)/this.zoom,n=2*e,s=this.aspect*n,r=-.5*s;const a=this.view;if(this.view!==null&&this.view.enabled){const l=a.fullWidth,h=a.fullHeight;r+=a.offsetX*s/l,e-=a.offsetY*n/h,s*=a.width/l,n*=a.height/h}const o=this.filmOffset;o!==0&&(r+=t*o/this.getFilmWidth()),this.projectionMatrix.makePerspective(r,r+s,e,e-n,t,this.far,this.coordinateSystem),this.projectionMatrixInverse.copy(this.projectionMatrix).invert()}toJSON(t){const e=super.toJSON(t);return e.object.fov=this.fov,e.object.zoom=this.zoom,e.object.near=this.near,e.object.far=this.far,e.object.focus=this.focus,e.object.aspect=this.aspect,this.view!==null&&(e.object.view=Object.assign({},this.view)),e.object.filmGauge=this.filmGauge,e.object.filmOffset=this.filmOffset,e}}const fi=-90,pi=1;class Qh extends me{constructor(t,e,n){super(),this.type="CubeCamera",this.renderTarget=n,this.coordinateSystem=null,this.activeMipmapLevel=0;const s=new Ve(fi,pi,t,e);s.layers=this.layers,this.add(s);const r=new Ve(fi,pi,t,e);r.layers=this.layers,this.add(r);const a=new Ve(fi,pi,t,e);a.layers=this.layers,this.add(a);const o=new Ve(fi,pi,t,e);o.layers=this.layers,this.add(o);const l=new Ve(fi,pi,t,e);l.layers=this.layers,this.add(l);const h=new Ve(fi,pi,t,e);h.layers=this.layers,this.add(h)}updateCoordinateSystem(){const t=this.coordinateSystem,e=this.children.concat(),[n,s,r,a,o,l]=e;for(const h of e)this.remove(h);if(t===vn)n.up.set(0,1,0),n.lookAt(1,0,0),s.up.set(0,1,0),s.lookAt(-1,0,0),r.up.set(0,0,-1),r.lookAt(0,1,0),a.up.set(0,0,1),a.lookAt(0,-1,0),o.up.set(0,1,0),o.lookAt(0,0,1),l.up.set(0,1,0),l.lookAt(0,0,-1);else if(t===$s)n.up.set(0,-1,0),n.lookAt(-1,0,0),s.up.set(0,-1,0),s.lookAt(1,0,0),r.up.set(0,0,1),r.lookAt(0,1,0),a.up.set(0,0,-1),a.lookAt(0,-1,0),o.up.set(0,-1,0),o.lookAt(0,0,1),l.up.set(0,-1,0),l.lookAt(0,0,-1);else throw new Error("THREE.CubeCamera.updateCoordinateSystem(): Invalid coordinate system: "+t);for(const h of e)this.add(h),h.updateMatrixWorld()}update(t,e){this.parent===null&&this.updateMatrixWorld();const{renderTarget:n,activeMipmapLevel:s}=this;this.coordinateSystem!==t.coordinateSystem&&(this.coordinateSystem=t.coordinateSystem,this.updateCoordinateSystem());const[r,a,o,l,h,d]=this.children,c=t.getRenderTarget(),u=t.getActiveCubeFace(),f=t.getActiveMipmapLevel(),g=t.xr.enabled;t.xr.enabled=!1;const v=n.texture.generateMipmaps;n.texture.generateMipmaps=!1,t.setRenderTarget(n,0,s),t.render(e,r),t.setRenderTarget(n,1,s),t.render(e,a),t.setRenderTarget(n,2,s),t.render(e,o),t.setRenderTarget(n,3,s),t.render(e,l),t.setRenderTarget(n,4,s),t.render(e,h),n.texture.generateMipmaps=v,t.setRenderTarget(n,5,s),t.render(e,d),t.setRenderTarget(c,u,f),t.xr.enabled=g,n.texture.needsPMREMUpdate=!0}}class Ql extends be{constructor(t,e,n,s,r,a,o,l,h,d){t=t!==void 0?t:[],e=e!==void 0?e:Ci,super(t,e,n,s,r,a,o,l,h,d),this.isCubeTexture=!0,this.flipY=!1}get images(){return this.image}set images(t){this.image=t}}class tu extends $n{constructor(t=1,e={}){super(t,t,e),this.isWebGLCubeRenderTarget=!0;const n={width:t,height:t,depth:1},s=[n,n,n,n,n,n];this.texture=new Ql(s,e.mapping,e.wrapS,e.wrapT,e.magFilter,e.minFilter,e.format,e.type,e.anisotropy,e.colorSpace),this.texture.isRenderTargetTexture=!0,this.texture.generateMipmaps=e.generateMipmaps!==void 0?e.generateMipmaps:!1,this.texture.minFilter=e.minFilter!==void 0?e.minFilter:We}fromEquirectangularTexture(t,e){this.texture.type=e.type,this.texture.colorSpace=e.colorSpace,this.texture.generateMipmaps=e.generateMipmaps,this.texture.minFilter=e.minFilter,this.texture.magFilter=e.magFilter;const n={uniforms:{tEquirect:{value:null}},vertexShader:`

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
			`},s=new Te(5,5,5),r=new an({name:"CubemapFromEquirect",uniforms:Ii(n.uniforms),vertexShader:n.vertexShader,fragmentShader:n.fragmentShader,side:Pe,blending:Ln});r.uniforms.tEquirect.value=e;const a=new Ct(s,r),o=e.minFilter;return e.minFilter===jn&&(e.minFilter=We),new Qh(1,10,this).update(t,a),e.minFilter=o,a.geometry.dispose(),a.material.dispose(),this}clear(t,e,n,s){const r=t.getRenderTarget();for(let a=0;a<6;a++)t.setRenderTarget(this,a),t.clear(e,n,s);t.setRenderTarget(r)}}const Ir=new R,eu=new R,nu=new Ot;class Vn{constructor(t=new R(1,0,0),e=0){this.isPlane=!0,this.normal=t,this.constant=e}set(t,e){return this.normal.copy(t),this.constant=e,this}setComponents(t,e,n,s){return this.normal.set(t,e,n),this.constant=s,this}setFromNormalAndCoplanarPoint(t,e){return this.normal.copy(t),this.constant=-e.dot(this.normal),this}setFromCoplanarPoints(t,e,n){const s=Ir.subVectors(n,e).cross(eu.subVectors(t,e)).normalize();return this.setFromNormalAndCoplanarPoint(s,t),this}copy(t){return this.normal.copy(t.normal),this.constant=t.constant,this}normalize(){const t=1/this.normal.length();return this.normal.multiplyScalar(t),this.constant*=t,this}negate(){return this.constant*=-1,this.normal.negate(),this}distanceToPoint(t){return this.normal.dot(t)+this.constant}distanceToSphere(t){return this.distanceToPoint(t.center)-t.radius}projectPoint(t,e){return e.copy(t).addScaledVector(this.normal,-this.distanceToPoint(t))}intersectLine(t,e){const n=t.delta(Ir),s=this.normal.dot(n);if(s===0)return this.distanceToPoint(t.start)===0?e.copy(t.start):null;const r=-(t.start.dot(this.normal)+this.constant)/s;return r<0||r>1?null:e.copy(t.start).addScaledVector(n,r)}intersectsLine(t){const e=this.distanceToPoint(t.start),n=this.distanceToPoint(t.end);return e<0&&n>0||n<0&&e>0}intersectsBox(t){return t.intersectsPlane(this)}intersectsSphere(t){return t.intersectsPlane(this)}coplanarPoint(t){return t.copy(this.normal).multiplyScalar(-this.constant)}applyMatrix4(t,e){const n=e||nu.getNormalMatrix(t),s=this.coplanarPoint(Ir).applyMatrix4(t),r=this.normal.applyMatrix3(n).normalize();return this.constant=-s.dot(r),this}translate(t){return this.constant-=t.dot(this.normal),this}equals(t){return t.normal.equals(this.normal)&&t.constant===this.constant}clone(){return new this.constructor().copy(this)}}const kn=new Oi,Cs=new R;class qa{constructor(t=new Vn,e=new Vn,n=new Vn,s=new Vn,r=new Vn,a=new Vn){this.planes=[t,e,n,s,r,a]}set(t,e,n,s,r,a){const o=this.planes;return o[0].copy(t),o[1].copy(e),o[2].copy(n),o[3].copy(s),o[4].copy(r),o[5].copy(a),this}copy(t){const e=this.planes;for(let n=0;n<6;n++)e[n].copy(t.planes[n]);return this}setFromProjectionMatrix(t,e=vn){const n=this.planes,s=t.elements,r=s[0],a=s[1],o=s[2],l=s[3],h=s[4],d=s[5],c=s[6],u=s[7],f=s[8],g=s[9],v=s[10],m=s[11],p=s[12],y=s[13],_=s[14],S=s[15];if(n[0].setComponents(l-r,u-h,m-f,S-p).normalize(),n[1].setComponents(l+r,u+h,m+f,S+p).normalize(),n[2].setComponents(l+a,u+d,m+g,S+y).normalize(),n[3].setComponents(l-a,u-d,m-g,S-y).normalize(),n[4].setComponents(l-o,u-c,m-v,S-_).normalize(),e===vn)n[5].setComponents(l+o,u+c,m+v,S+_).normalize();else if(e===$s)n[5].setComponents(o,c,v,_).normalize();else throw new Error("THREE.Frustum.setFromProjectionMatrix(): Invalid coordinate system: "+e);return this}intersectsObject(t){if(t.boundingSphere!==void 0)t.boundingSphere===null&&t.computeBoundingSphere(),kn.copy(t.boundingSphere).applyMatrix4(t.matrixWorld);else{const e=t.geometry;e.boundingSphere===null&&e.computeBoundingSphere(),kn.copy(e.boundingSphere).applyMatrix4(t.matrixWorld)}return this.intersectsSphere(kn)}intersectsSprite(t){return kn.center.set(0,0,0),kn.radius=.7071067811865476,kn.applyMatrix4(t.matrixWorld),this.intersectsSphere(kn)}intersectsSphere(t){const e=this.planes,n=t.center,s=-t.radius;for(let r=0;r<6;r++)if(e[r].distanceToPoint(n)<s)return!1;return!0}intersectsBox(t){const e=this.planes;for(let n=0;n<6;n++){const s=e[n];if(Cs.x=s.normal.x>0?t.max.x:t.min.x,Cs.y=s.normal.y>0?t.max.y:t.min.y,Cs.z=s.normal.z>0?t.max.z:t.min.z,s.distanceToPoint(Cs)<0)return!1}return!0}containsPoint(t){const e=this.planes;for(let n=0;n<6;n++)if(e[n].distanceToPoint(t)<0)return!1;return!0}clone(){return new this.constructor().copy(this)}}function tc(){let i=null,t=!1,e=null,n=null;function s(r,a){e(r,a),n=i.requestAnimationFrame(s)}return{start:function(){t!==!0&&e!==null&&(n=i.requestAnimationFrame(s),t=!0)},stop:function(){i.cancelAnimationFrame(n),t=!1},setAnimationLoop:function(r){e=r},setContext:function(r){i=r}}}function iu(i){const t=new WeakMap;function e(o,l){const h=o.array,d=o.usage,c=h.byteLength,u=i.createBuffer();i.bindBuffer(l,u),i.bufferData(l,h,d),o.onUploadCallback();let f;if(h instanceof Float32Array)f=i.FLOAT;else if(h instanceof Uint16Array)o.isFloat16BufferAttribute?f=i.HALF_FLOAT:f=i.UNSIGNED_SHORT;else if(h instanceof Int16Array)f=i.SHORT;else if(h instanceof Uint32Array)f=i.UNSIGNED_INT;else if(h instanceof Int32Array)f=i.INT;else if(h instanceof Int8Array)f=i.BYTE;else if(h instanceof Uint8Array)f=i.UNSIGNED_BYTE;else if(h instanceof Uint8ClampedArray)f=i.UNSIGNED_BYTE;else throw new Error("THREE.WebGLAttributes: Unsupported buffer data format: "+h);return{buffer:u,type:f,bytesPerElement:h.BYTES_PER_ELEMENT,version:o.version,size:c}}function n(o,l,h){const d=l.array,c=l.updateRanges;if(i.bindBuffer(h,o),c.length===0)i.bufferSubData(h,0,d);else{c.sort((f,g)=>f.start-g.start);let u=0;for(let f=1;f<c.length;f++){const g=c[u],v=c[f];v.start<=g.start+g.count+1?g.count=Math.max(g.count,v.start+v.count-g.start):(++u,c[u]=v)}c.length=u+1;for(let f=0,g=c.length;f<g;f++){const v=c[f];i.bufferSubData(h,v.start*d.BYTES_PER_ELEMENT,d,v.start,v.count)}l.clearUpdateRanges()}l.onUploadCallback()}function s(o){return o.isInterleavedBufferAttribute&&(o=o.data),t.get(o)}function r(o){o.isInterleavedBufferAttribute&&(o=o.data);const l=t.get(o);l&&(i.deleteBuffer(l.buffer),t.delete(o))}function a(o,l){if(o.isInterleavedBufferAttribute&&(o=o.data),o.isGLBufferAttribute){const d=t.get(o);(!d||d.version<o.version)&&t.set(o,{buffer:o.buffer,type:o.type,bytesPerElement:o.elementSize,version:o.version});return}const h=t.get(o);if(h===void 0)t.set(o,e(o,l));else if(h.version<o.version){if(h.size!==o.array.byteLength)throw new Error("THREE.WebGLAttributes: The size of the buffer attribute's array buffer does not match the original size. Resizing buffer attributes is not supported.");n(h.buffer,o,l),h.version=o.version}}return{get:s,remove:r,update:a}}class Qn extends Le{constructor(t=1,e=1,n=1,s=1){super(),this.type="PlaneGeometry",this.parameters={width:t,height:e,widthSegments:n,heightSegments:s};const r=t/2,a=e/2,o=Math.floor(n),l=Math.floor(s),h=o+1,d=l+1,c=t/o,u=e/l,f=[],g=[],v=[],m=[];for(let p=0;p<d;p++){const y=p*u-a;for(let _=0;_<h;_++){const S=_*c-r;g.push(S,-y,0),v.push(0,0,1),m.push(_/o),m.push(1-p/l)}}for(let p=0;p<l;p++)for(let y=0;y<o;y++){const _=y+h*p,S=y+h*(p+1),P=y+1+h*(p+1),T=y+1+h*p;f.push(_,S,T),f.push(S,P,T)}this.setIndex(f),this.setAttribute("position",new le(g,3)),this.setAttribute("normal",new le(v,3)),this.setAttribute("uv",new le(m,2))}copy(t){return super.copy(t),this.parameters=Object.assign({},t.parameters),this}static fromJSON(t){return new Qn(t.width,t.height,t.widthSegments,t.heightSegments)}}var su=`#ifdef USE_ALPHAHASH
	if ( diffuseColor.a < getAlphaHashThreshold( vPosition ) ) discard;
#endif`,ru=`#ifdef USE_ALPHAHASH
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
#endif`,au=`#ifdef USE_ALPHAMAP
	diffuseColor.a *= texture2D( alphaMap, vAlphaMapUv ).g;
#endif`,ou=`#ifdef USE_ALPHAMAP
	uniform sampler2D alphaMap;
#endif`,lu=`#ifdef USE_ALPHATEST
	#ifdef ALPHA_TO_COVERAGE
	diffuseColor.a = smoothstep( alphaTest, alphaTest + fwidth( diffuseColor.a ), diffuseColor.a );
	if ( diffuseColor.a == 0.0 ) discard;
	#else
	if ( diffuseColor.a < alphaTest ) discard;
	#endif
#endif`,cu=`#ifdef USE_ALPHATEST
	uniform float alphaTest;
#endif`,hu=`#ifdef USE_AOMAP
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
#endif`,uu=`#ifdef USE_AOMAP
	uniform sampler2D aoMap;
	uniform float aoMapIntensity;
#endif`,du=`#ifdef USE_BATCHING
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
#endif`,fu=`#ifdef USE_BATCHING
	mat4 batchingMatrix = getBatchingMatrix( getIndirectIndex( gl_DrawID ) );
#endif`,pu=`vec3 transformed = vec3( position );
#ifdef USE_ALPHAHASH
	vPosition = vec3( position );
#endif`,mu=`vec3 objectNormal = vec3( normal );
#ifdef USE_TANGENT
	vec3 objectTangent = vec3( tangent.xyz );
#endif`,gu=`float G_BlinnPhong_Implicit( ) {
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
} // validated`,_u=`#ifdef USE_IRIDESCENCE
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
#endif`,xu=`#ifdef USE_BUMPMAP
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
#endif`,vu=`#if NUM_CLIPPING_PLANES > 0
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
#endif`,Mu=`#if NUM_CLIPPING_PLANES > 0
	varying vec3 vClipPosition;
	uniform vec4 clippingPlanes[ NUM_CLIPPING_PLANES ];
#endif`,yu=`#if NUM_CLIPPING_PLANES > 0
	varying vec3 vClipPosition;
#endif`,Su=`#if NUM_CLIPPING_PLANES > 0
	vClipPosition = - mvPosition.xyz;
#endif`,wu=`#if defined( USE_COLOR_ALPHA )
	diffuseColor *= vColor;
#elif defined( USE_COLOR )
	diffuseColor.rgb *= vColor;
#endif`,Eu=`#if defined( USE_COLOR_ALPHA )
	varying vec4 vColor;
#elif defined( USE_COLOR )
	varying vec3 vColor;
#endif`,bu=`#if defined( USE_COLOR_ALPHA )
	varying vec4 vColor;
#elif defined( USE_COLOR ) || defined( USE_INSTANCING_COLOR ) || defined( USE_BATCHING_COLOR )
	varying vec3 vColor;
#endif`,Tu=`#if defined( USE_COLOR_ALPHA )
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
#endif`,Au=`#define PI 3.141592653589793
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
} // validated`,Ru=`#ifdef ENVMAP_TYPE_CUBE_UV
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
#endif`,Cu=`vec3 transformedNormal = objectNormal;
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
#endif`,Pu=`#ifdef USE_DISPLACEMENTMAP
	uniform sampler2D displacementMap;
	uniform float displacementScale;
	uniform float displacementBias;
#endif`,Lu=`#ifdef USE_DISPLACEMENTMAP
	transformed += normalize( objectNormal ) * ( texture2D( displacementMap, vDisplacementMapUv ).x * displacementScale + displacementBias );
#endif`,Du=`#ifdef USE_EMISSIVEMAP
	vec4 emissiveColor = texture2D( emissiveMap, vEmissiveMapUv );
	totalEmissiveRadiance *= emissiveColor.rgb;
#endif`,Iu=`#ifdef USE_EMISSIVEMAP
	uniform sampler2D emissiveMap;
#endif`,Uu="gl_FragColor = linearToOutputTexel( gl_FragColor );",Nu=`
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
}`,Fu=`#ifdef USE_ENVMAP
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
#endif`,Ou=`#ifdef USE_ENVMAP
	uniform float envMapIntensity;
	uniform float flipEnvMap;
	uniform mat3 envMapRotation;
	#ifdef ENVMAP_TYPE_CUBE
		uniform samplerCube envMap;
	#else
		uniform sampler2D envMap;
	#endif
	
#endif`,Bu=`#ifdef USE_ENVMAP
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
#endif`,ku=`#ifdef USE_ENVMAP
	#if defined( USE_BUMPMAP ) || defined( USE_NORMALMAP ) || defined( PHONG ) || defined( LAMBERT )
		#define ENV_WORLDPOS
	#endif
	#ifdef ENV_WORLDPOS
		
		varying vec3 vWorldPosition;
	#else
		varying vec3 vReflect;
		uniform float refractionRatio;
	#endif
#endif`,zu=`#ifdef USE_ENVMAP
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
#endif`,Hu=`#ifdef USE_FOG
	vFogDepth = - mvPosition.z;
#endif`,Gu=`#ifdef USE_FOG
	varying float vFogDepth;
#endif`,Vu=`#ifdef USE_FOG
	#ifdef FOG_EXP2
		float fogFactor = 1.0 - exp( - fogDensity * fogDensity * vFogDepth * vFogDepth );
	#else
		float fogFactor = smoothstep( fogNear, fogFar, vFogDepth );
	#endif
	gl_FragColor.rgb = mix( gl_FragColor.rgb, fogColor, fogFactor );
#endif`,Wu=`#ifdef USE_FOG
	uniform vec3 fogColor;
	varying float vFogDepth;
	#ifdef FOG_EXP2
		uniform float fogDensity;
	#else
		uniform float fogNear;
		uniform float fogFar;
	#endif
#endif`,Xu=`#ifdef USE_GRADIENTMAP
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
}`,Yu=`#ifdef USE_LIGHTMAP
	uniform sampler2D lightMap;
	uniform float lightMapIntensity;
#endif`,qu=`LambertMaterial material;
material.diffuseColor = diffuseColor.rgb;
material.specularStrength = specularStrength;`,Ku=`varying vec3 vViewPosition;
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
#define RE_IndirectDiffuse		RE_IndirectDiffuse_Lambert`,ju=`uniform bool receiveShadow;
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
#endif`,Zu=`#ifdef USE_ENVMAP
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
#endif`,$u=`ToonMaterial material;
material.diffuseColor = diffuseColor.rgb;`,Ju=`varying vec3 vViewPosition;
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
#define RE_IndirectDiffuse		RE_IndirectDiffuse_Toon`,Qu=`BlinnPhongMaterial material;
material.diffuseColor = diffuseColor.rgb;
material.specularColor = specular;
material.specularShininess = shininess;
material.specularStrength = specularStrength;`,td=`varying vec3 vViewPosition;
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
#define RE_IndirectDiffuse		RE_IndirectDiffuse_BlinnPhong`,ed=`PhysicalMaterial material;
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
#endif`,nd=`struct PhysicalMaterial {
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
}`,id=`
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
#endif`,sd=`#if defined( RE_IndirectDiffuse )
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
#endif`,rd=`#if defined( RE_IndirectDiffuse )
	RE_IndirectDiffuse( irradiance, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
#endif
#if defined( RE_IndirectSpecular )
	RE_IndirectSpecular( radiance, iblIrradiance, clearcoatRadiance, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
#endif`,ad=`#if defined( USE_LOGDEPTHBUF )
	gl_FragDepth = vIsPerspective == 0.0 ? gl_FragCoord.z : log2( vFragDepth ) * logDepthBufFC * 0.5;
#endif`,od=`#if defined( USE_LOGDEPTHBUF )
	uniform float logDepthBufFC;
	varying float vFragDepth;
	varying float vIsPerspective;
#endif`,ld=`#ifdef USE_LOGDEPTHBUF
	varying float vFragDepth;
	varying float vIsPerspective;
#endif`,cd=`#ifdef USE_LOGDEPTHBUF
	vFragDepth = 1.0 + gl_Position.w;
	vIsPerspective = float( isPerspectiveMatrix( projectionMatrix ) );
#endif`,hd=`#ifdef USE_MAP
	vec4 sampledDiffuseColor = texture2D( map, vMapUv );
	#ifdef DECODE_VIDEO_TEXTURE
		sampledDiffuseColor = vec4( mix( pow( sampledDiffuseColor.rgb * 0.9478672986 + vec3( 0.0521327014 ), vec3( 2.4 ) ), sampledDiffuseColor.rgb * 0.0773993808, vec3( lessThanEqual( sampledDiffuseColor.rgb, vec3( 0.04045 ) ) ) ), sampledDiffuseColor.w );
	
	#endif
	diffuseColor *= sampledDiffuseColor;
#endif`,ud=`#ifdef USE_MAP
	uniform sampler2D map;
#endif`,dd=`#if defined( USE_MAP ) || defined( USE_ALPHAMAP )
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
#endif`,fd=`#if defined( USE_POINTS_UV )
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
#endif`,pd=`float metalnessFactor = metalness;
#ifdef USE_METALNESSMAP
	vec4 texelMetalness = texture2D( metalnessMap, vMetalnessMapUv );
	metalnessFactor *= texelMetalness.b;
#endif`,md=`#ifdef USE_METALNESSMAP
	uniform sampler2D metalnessMap;
#endif`,gd=`#ifdef USE_INSTANCING_MORPH
	float morphTargetInfluences[ MORPHTARGETS_COUNT ];
	float morphTargetBaseInfluence = texelFetch( morphTexture, ivec2( 0, gl_InstanceID ), 0 ).r;
	for ( int i = 0; i < MORPHTARGETS_COUNT; i ++ ) {
		morphTargetInfluences[i] =  texelFetch( morphTexture, ivec2( i + 1, gl_InstanceID ), 0 ).r;
	}
#endif`,_d=`#if defined( USE_MORPHCOLORS )
	vColor *= morphTargetBaseInfluence;
	for ( int i = 0; i < MORPHTARGETS_COUNT; i ++ ) {
		#if defined( USE_COLOR_ALPHA )
			if ( morphTargetInfluences[ i ] != 0.0 ) vColor += getMorph( gl_VertexID, i, 2 ) * morphTargetInfluences[ i ];
		#elif defined( USE_COLOR )
			if ( morphTargetInfluences[ i ] != 0.0 ) vColor += getMorph( gl_VertexID, i, 2 ).rgb * morphTargetInfluences[ i ];
		#endif
	}
#endif`,xd=`#ifdef USE_MORPHNORMALS
	objectNormal *= morphTargetBaseInfluence;
	for ( int i = 0; i < MORPHTARGETS_COUNT; i ++ ) {
		if ( morphTargetInfluences[ i ] != 0.0 ) objectNormal += getMorph( gl_VertexID, i, 1 ).xyz * morphTargetInfluences[ i ];
	}
#endif`,vd=`#ifdef USE_MORPHTARGETS
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
#endif`,Md=`#ifdef USE_MORPHTARGETS
	transformed *= morphTargetBaseInfluence;
	for ( int i = 0; i < MORPHTARGETS_COUNT; i ++ ) {
		if ( morphTargetInfluences[ i ] != 0.0 ) transformed += getMorph( gl_VertexID, i, 0 ).xyz * morphTargetInfluences[ i ];
	}
#endif`,yd=`float faceDirection = gl_FrontFacing ? 1.0 : - 1.0;
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
vec3 nonPerturbedNormal = normal;`,Sd=`#ifdef USE_NORMALMAP_OBJECTSPACE
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
#endif`,wd=`#ifndef FLAT_SHADED
	varying vec3 vNormal;
	#ifdef USE_TANGENT
		varying vec3 vTangent;
		varying vec3 vBitangent;
	#endif
#endif`,Ed=`#ifndef FLAT_SHADED
	varying vec3 vNormal;
	#ifdef USE_TANGENT
		varying vec3 vTangent;
		varying vec3 vBitangent;
	#endif
#endif`,bd=`#ifndef FLAT_SHADED
	vNormal = normalize( transformedNormal );
	#ifdef USE_TANGENT
		vTangent = normalize( transformedTangent );
		vBitangent = normalize( cross( vNormal, vTangent ) * tangent.w );
	#endif
#endif`,Td=`#ifdef USE_NORMALMAP
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
#endif`,Ad=`#ifdef USE_CLEARCOAT
	vec3 clearcoatNormal = nonPerturbedNormal;
#endif`,Rd=`#ifdef USE_CLEARCOAT_NORMALMAP
	vec3 clearcoatMapN = texture2D( clearcoatNormalMap, vClearcoatNormalMapUv ).xyz * 2.0 - 1.0;
	clearcoatMapN.xy *= clearcoatNormalScale;
	clearcoatNormal = normalize( tbn2 * clearcoatMapN );
#endif`,Cd=`#ifdef USE_CLEARCOATMAP
	uniform sampler2D clearcoatMap;
#endif
#ifdef USE_CLEARCOAT_NORMALMAP
	uniform sampler2D clearcoatNormalMap;
	uniform vec2 clearcoatNormalScale;
#endif
#ifdef USE_CLEARCOAT_ROUGHNESSMAP
	uniform sampler2D clearcoatRoughnessMap;
#endif`,Pd=`#ifdef USE_IRIDESCENCEMAP
	uniform sampler2D iridescenceMap;
#endif
#ifdef USE_IRIDESCENCE_THICKNESSMAP
	uniform sampler2D iridescenceThicknessMap;
#endif`,Ld=`#ifdef OPAQUE
diffuseColor.a = 1.0;
#endif
#ifdef USE_TRANSMISSION
diffuseColor.a *= material.transmissionAlpha;
#endif
gl_FragColor = vec4( outgoingLight, diffuseColor.a );`,Dd=`vec3 packNormalToRGB( const in vec3 normal ) {
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
}`,Id=`#ifdef PREMULTIPLIED_ALPHA
	gl_FragColor.rgb *= gl_FragColor.a;
#endif`,Ud=`vec4 mvPosition = vec4( transformed, 1.0 );
#ifdef USE_BATCHING
	mvPosition = batchingMatrix * mvPosition;
#endif
#ifdef USE_INSTANCING
	mvPosition = instanceMatrix * mvPosition;
#endif
mvPosition = modelViewMatrix * mvPosition;
gl_Position = projectionMatrix * mvPosition;`,Nd=`#ifdef DITHERING
	gl_FragColor.rgb = dithering( gl_FragColor.rgb );
#endif`,Fd=`#ifdef DITHERING
	vec3 dithering( vec3 color ) {
		float grid_position = rand( gl_FragCoord.xy );
		vec3 dither_shift_RGB = vec3( 0.25 / 255.0, -0.25 / 255.0, 0.25 / 255.0 );
		dither_shift_RGB = mix( 2.0 * dither_shift_RGB, -2.0 * dither_shift_RGB, grid_position );
		return color + dither_shift_RGB;
	}
#endif`,Od=`float roughnessFactor = roughness;
#ifdef USE_ROUGHNESSMAP
	vec4 texelRoughness = texture2D( roughnessMap, vRoughnessMapUv );
	roughnessFactor *= texelRoughness.g;
#endif`,Bd=`#ifdef USE_ROUGHNESSMAP
	uniform sampler2D roughnessMap;
#endif`,kd=`#if NUM_SPOT_LIGHT_COORDS > 0
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
#endif`,zd=`#if NUM_SPOT_LIGHT_COORDS > 0
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
#endif`,Hd=`#if ( defined( USE_SHADOWMAP ) && ( NUM_DIR_LIGHT_SHADOWS > 0 || NUM_POINT_LIGHT_SHADOWS > 0 ) ) || ( NUM_SPOT_LIGHT_COORDS > 0 )
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
#endif`,Gd=`float getShadowMask() {
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
}`,Vd=`#ifdef USE_SKINNING
	mat4 boneMatX = getBoneMatrix( skinIndex.x );
	mat4 boneMatY = getBoneMatrix( skinIndex.y );
	mat4 boneMatZ = getBoneMatrix( skinIndex.z );
	mat4 boneMatW = getBoneMatrix( skinIndex.w );
#endif`,Wd=`#ifdef USE_SKINNING
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
#endif`,Xd=`#ifdef USE_SKINNING
	vec4 skinVertex = bindMatrix * vec4( transformed, 1.0 );
	vec4 skinned = vec4( 0.0 );
	skinned += boneMatX * skinVertex * skinWeight.x;
	skinned += boneMatY * skinVertex * skinWeight.y;
	skinned += boneMatZ * skinVertex * skinWeight.z;
	skinned += boneMatW * skinVertex * skinWeight.w;
	transformed = ( bindMatrixInverse * skinned ).xyz;
#endif`,Yd=`#ifdef USE_SKINNING
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
#endif`,qd=`float specularStrength;
#ifdef USE_SPECULARMAP
	vec4 texelSpecular = texture2D( specularMap, vSpecularMapUv );
	specularStrength = texelSpecular.r;
#else
	specularStrength = 1.0;
#endif`,Kd=`#ifdef USE_SPECULARMAP
	uniform sampler2D specularMap;
#endif`,jd=`#if defined( TONE_MAPPING )
	gl_FragColor.rgb = toneMapping( gl_FragColor.rgb );
#endif`,Zd=`#ifndef saturate
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
vec3 CustomToneMapping( vec3 color ) { return color; }`,$d=`#ifdef USE_TRANSMISSION
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
#endif`,Jd=`#ifdef USE_TRANSMISSION
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
#endif`,Qd=`#if defined( USE_UV ) || defined( USE_ANISOTROPY )
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
#endif`,tf=`#if defined( USE_UV ) || defined( USE_ANISOTROPY )
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
#endif`,ef=`#if defined( USE_UV ) || defined( USE_ANISOTROPY )
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
#endif`,nf=`#if defined( USE_ENVMAP ) || defined( DISTANCE ) || defined ( USE_SHADOWMAP ) || defined ( USE_TRANSMISSION ) || NUM_SPOT_LIGHT_COORDS > 0
	vec4 worldPosition = vec4( transformed, 1.0 );
	#ifdef USE_BATCHING
		worldPosition = batchingMatrix * worldPosition;
	#endif
	#ifdef USE_INSTANCING
		worldPosition = instanceMatrix * worldPosition;
	#endif
	worldPosition = modelMatrix * worldPosition;
#endif`;const sf=`varying vec2 vUv;
uniform mat3 uvTransform;
void main() {
	vUv = ( uvTransform * vec3( uv, 1 ) ).xy;
	gl_Position = vec4( position.xy, 1.0, 1.0 );
}`,rf=`uniform sampler2D t2D;
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
}`,af=`varying vec3 vWorldDirection;
#include <common>
void main() {
	vWorldDirection = transformDirection( position, modelMatrix );
	#include <begin_vertex>
	#include <project_vertex>
	gl_Position.z = gl_Position.w;
}`,of=`#ifdef ENVMAP_TYPE_CUBE
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
}`,lf=`varying vec3 vWorldDirection;
#include <common>
void main() {
	vWorldDirection = transformDirection( position, modelMatrix );
	#include <begin_vertex>
	#include <project_vertex>
	gl_Position.z = gl_Position.w;
}`,cf=`uniform samplerCube tCube;
uniform float tFlip;
uniform float opacity;
varying vec3 vWorldDirection;
void main() {
	vec4 texColor = textureCube( tCube, vec3( tFlip * vWorldDirection.x, vWorldDirection.yz ) );
	gl_FragColor = texColor;
	gl_FragColor.a *= opacity;
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
}`,hf=`#include <common>
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
}`,uf=`#if DEPTH_PACKING == 3200
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
}`,df=`#define DISTANCE
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
}`,ff=`#define DISTANCE
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
}`,pf=`varying vec3 vWorldDirection;
#include <common>
void main() {
	vWorldDirection = transformDirection( position, modelMatrix );
	#include <begin_vertex>
	#include <project_vertex>
}`,mf=`uniform sampler2D tEquirect;
varying vec3 vWorldDirection;
#include <common>
void main() {
	vec3 direction = normalize( vWorldDirection );
	vec2 sampleUV = equirectUv( direction );
	gl_FragColor = texture2D( tEquirect, sampleUV );
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
}`,gf=`uniform float scale;
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
}`,_f=`uniform vec3 diffuse;
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
}`,xf=`#include <common>
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
}`,vf=`uniform vec3 diffuse;
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
}`,Mf=`#define LAMBERT
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
}`,yf=`#define LAMBERT
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
}`,Sf=`#define MATCAP
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
}`,wf=`#define MATCAP
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
}`,Ef=`#define NORMAL
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
}`,bf=`#define NORMAL
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
}`,Tf=`#define PHONG
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
}`,Af=`#define PHONG
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
}`,Rf=`#define STANDARD
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
}`,Cf=`#define STANDARD
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
}`,Pf=`#define TOON
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
}`,Lf=`#define TOON
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
}`,Df=`uniform float size;
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
}`,If=`uniform vec3 diffuse;
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
}`,Uf=`#include <common>
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
}`,Nf=`uniform vec3 color;
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
}`,Ff=`uniform float rotation;
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
}`,Of=`uniform vec3 diffuse;
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
}`,Ft={alphahash_fragment:su,alphahash_pars_fragment:ru,alphamap_fragment:au,alphamap_pars_fragment:ou,alphatest_fragment:lu,alphatest_pars_fragment:cu,aomap_fragment:hu,aomap_pars_fragment:uu,batching_pars_vertex:du,batching_vertex:fu,begin_vertex:pu,beginnormal_vertex:mu,bsdfs:gu,iridescence_fragment:_u,bumpmap_pars_fragment:xu,clipping_planes_fragment:vu,clipping_planes_pars_fragment:Mu,clipping_planes_pars_vertex:yu,clipping_planes_vertex:Su,color_fragment:wu,color_pars_fragment:Eu,color_pars_vertex:bu,color_vertex:Tu,common:Au,cube_uv_reflection_fragment:Ru,defaultnormal_vertex:Cu,displacementmap_pars_vertex:Pu,displacementmap_vertex:Lu,emissivemap_fragment:Du,emissivemap_pars_fragment:Iu,colorspace_fragment:Uu,colorspace_pars_fragment:Nu,envmap_fragment:Fu,envmap_common_pars_fragment:Ou,envmap_pars_fragment:Bu,envmap_pars_vertex:ku,envmap_physical_pars_fragment:Zu,envmap_vertex:zu,fog_vertex:Hu,fog_pars_vertex:Gu,fog_fragment:Vu,fog_pars_fragment:Wu,gradientmap_pars_fragment:Xu,lightmap_pars_fragment:Yu,lights_lambert_fragment:qu,lights_lambert_pars_fragment:Ku,lights_pars_begin:ju,lights_toon_fragment:$u,lights_toon_pars_fragment:Ju,lights_phong_fragment:Qu,lights_phong_pars_fragment:td,lights_physical_fragment:ed,lights_physical_pars_fragment:nd,lights_fragment_begin:id,lights_fragment_maps:sd,lights_fragment_end:rd,logdepthbuf_fragment:ad,logdepthbuf_pars_fragment:od,logdepthbuf_pars_vertex:ld,logdepthbuf_vertex:cd,map_fragment:hd,map_pars_fragment:ud,map_particle_fragment:dd,map_particle_pars_fragment:fd,metalnessmap_fragment:pd,metalnessmap_pars_fragment:md,morphinstance_vertex:gd,morphcolor_vertex:_d,morphnormal_vertex:xd,morphtarget_pars_vertex:vd,morphtarget_vertex:Md,normal_fragment_begin:yd,normal_fragment_maps:Sd,normal_pars_fragment:wd,normal_pars_vertex:Ed,normal_vertex:bd,normalmap_pars_fragment:Td,clearcoat_normal_fragment_begin:Ad,clearcoat_normal_fragment_maps:Rd,clearcoat_pars_fragment:Cd,iridescence_pars_fragment:Pd,opaque_fragment:Ld,packing:Dd,premultiplied_alpha_fragment:Id,project_vertex:Ud,dithering_fragment:Nd,dithering_pars_fragment:Fd,roughnessmap_fragment:Od,roughnessmap_pars_fragment:Bd,shadowmap_pars_fragment:kd,shadowmap_pars_vertex:zd,shadowmap_vertex:Hd,shadowmask_pars_fragment:Gd,skinbase_vertex:Vd,skinning_pars_vertex:Wd,skinning_vertex:Xd,skinnormal_vertex:Yd,specularmap_fragment:qd,specularmap_pars_fragment:Kd,tonemapping_fragment:jd,tonemapping_pars_fragment:Zd,transmission_fragment:$d,transmission_pars_fragment:Jd,uv_pars_fragment:Qd,uv_pars_vertex:tf,uv_vertex:ef,worldpos_vertex:nf,background_vert:sf,background_frag:rf,backgroundCube_vert:af,backgroundCube_frag:of,cube_vert:lf,cube_frag:cf,depth_vert:hf,depth_frag:uf,distanceRGBA_vert:df,distanceRGBA_frag:ff,equirect_vert:pf,equirect_frag:mf,linedashed_vert:gf,linedashed_frag:_f,meshbasic_vert:xf,meshbasic_frag:vf,meshlambert_vert:Mf,meshlambert_frag:yf,meshmatcap_vert:Sf,meshmatcap_frag:wf,meshnormal_vert:Ef,meshnormal_frag:bf,meshphong_vert:Tf,meshphong_frag:Af,meshphysical_vert:Rf,meshphysical_frag:Cf,meshtoon_vert:Pf,meshtoon_frag:Lf,points_vert:Df,points_frag:If,shadow_vert:Uf,shadow_frag:Nf,sprite_vert:Ff,sprite_frag:Of},st={common:{diffuse:{value:new Pt(16777215)},opacity:{value:1},map:{value:null},mapTransform:{value:new Ot},alphaMap:{value:null},alphaMapTransform:{value:new Ot},alphaTest:{value:0}},specularmap:{specularMap:{value:null},specularMapTransform:{value:new Ot}},envmap:{envMap:{value:null},envMapRotation:{value:new Ot},flipEnvMap:{value:-1},reflectivity:{value:1},ior:{value:1.5},refractionRatio:{value:.98}},aomap:{aoMap:{value:null},aoMapIntensity:{value:1},aoMapTransform:{value:new Ot}},lightmap:{lightMap:{value:null},lightMapIntensity:{value:1},lightMapTransform:{value:new Ot}},bumpmap:{bumpMap:{value:null},bumpMapTransform:{value:new Ot},bumpScale:{value:1}},normalmap:{normalMap:{value:null},normalMapTransform:{value:new Ot},normalScale:{value:new Ht(1,1)}},displacementmap:{displacementMap:{value:null},displacementMapTransform:{value:new Ot},displacementScale:{value:1},displacementBias:{value:0}},emissivemap:{emissiveMap:{value:null},emissiveMapTransform:{value:new Ot}},metalnessmap:{metalnessMap:{value:null},metalnessMapTransform:{value:new Ot}},roughnessmap:{roughnessMap:{value:null},roughnessMapTransform:{value:new Ot}},gradientmap:{gradientMap:{value:null}},fog:{fogDensity:{value:25e-5},fogNear:{value:1},fogFar:{value:2e3},fogColor:{value:new Pt(16777215)}},lights:{ambientLightColor:{value:[]},lightProbe:{value:[]},directionalLights:{value:[],properties:{direction:{},color:{}}},directionalLightShadows:{value:[],properties:{shadowIntensity:1,shadowBias:{},shadowNormalBias:{},shadowRadius:{},shadowMapSize:{}}},directionalShadowMap:{value:[]},directionalShadowMatrix:{value:[]},spotLights:{value:[],properties:{color:{},position:{},direction:{},distance:{},coneCos:{},penumbraCos:{},decay:{}}},spotLightShadows:{value:[],properties:{shadowIntensity:1,shadowBias:{},shadowNormalBias:{},shadowRadius:{},shadowMapSize:{}}},spotLightMap:{value:[]},spotShadowMap:{value:[]},spotLightMatrix:{value:[]},pointLights:{value:[],properties:{color:{},position:{},decay:{},distance:{}}},pointLightShadows:{value:[],properties:{shadowIntensity:1,shadowBias:{},shadowNormalBias:{},shadowRadius:{},shadowMapSize:{},shadowCameraNear:{},shadowCameraFar:{}}},pointShadowMap:{value:[]},pointShadowMatrix:{value:[]},hemisphereLights:{value:[],properties:{direction:{},skyColor:{},groundColor:{}}},rectAreaLights:{value:[],properties:{color:{},position:{},width:{},height:{}}},ltc_1:{value:null},ltc_2:{value:null}},points:{diffuse:{value:new Pt(16777215)},opacity:{value:1},size:{value:1},scale:{value:1},map:{value:null},alphaMap:{value:null},alphaMapTransform:{value:new Ot},alphaTest:{value:0},uvTransform:{value:new Ot}},sprite:{diffuse:{value:new Pt(16777215)},opacity:{value:1},center:{value:new Ht(.5,.5)},rotation:{value:0},map:{value:null},mapTransform:{value:new Ot},alphaMap:{value:null},alphaMapTransform:{value:new Ot},alphaTest:{value:0}}},ln={basic:{uniforms:Ce([st.common,st.specularmap,st.envmap,st.aomap,st.lightmap,st.fog]),vertexShader:Ft.meshbasic_vert,fragmentShader:Ft.meshbasic_frag},lambert:{uniforms:Ce([st.common,st.specularmap,st.envmap,st.aomap,st.lightmap,st.emissivemap,st.bumpmap,st.normalmap,st.displacementmap,st.fog,st.lights,{emissive:{value:new Pt(0)}}]),vertexShader:Ft.meshlambert_vert,fragmentShader:Ft.meshlambert_frag},phong:{uniforms:Ce([st.common,st.specularmap,st.envmap,st.aomap,st.lightmap,st.emissivemap,st.bumpmap,st.normalmap,st.displacementmap,st.fog,st.lights,{emissive:{value:new Pt(0)},specular:{value:new Pt(1118481)},shininess:{value:30}}]),vertexShader:Ft.meshphong_vert,fragmentShader:Ft.meshphong_frag},standard:{uniforms:Ce([st.common,st.envmap,st.aomap,st.lightmap,st.emissivemap,st.bumpmap,st.normalmap,st.displacementmap,st.roughnessmap,st.metalnessmap,st.fog,st.lights,{emissive:{value:new Pt(0)},roughness:{value:1},metalness:{value:0},envMapIntensity:{value:1}}]),vertexShader:Ft.meshphysical_vert,fragmentShader:Ft.meshphysical_frag},toon:{uniforms:Ce([st.common,st.aomap,st.lightmap,st.emissivemap,st.bumpmap,st.normalmap,st.displacementmap,st.gradientmap,st.fog,st.lights,{emissive:{value:new Pt(0)}}]),vertexShader:Ft.meshtoon_vert,fragmentShader:Ft.meshtoon_frag},matcap:{uniforms:Ce([st.common,st.bumpmap,st.normalmap,st.displacementmap,st.fog,{matcap:{value:null}}]),vertexShader:Ft.meshmatcap_vert,fragmentShader:Ft.meshmatcap_frag},points:{uniforms:Ce([st.points,st.fog]),vertexShader:Ft.points_vert,fragmentShader:Ft.points_frag},dashed:{uniforms:Ce([st.common,st.fog,{scale:{value:1},dashSize:{value:1},totalSize:{value:2}}]),vertexShader:Ft.linedashed_vert,fragmentShader:Ft.linedashed_frag},depth:{uniforms:Ce([st.common,st.displacementmap]),vertexShader:Ft.depth_vert,fragmentShader:Ft.depth_frag},normal:{uniforms:Ce([st.common,st.bumpmap,st.normalmap,st.displacementmap,{opacity:{value:1}}]),vertexShader:Ft.meshnormal_vert,fragmentShader:Ft.meshnormal_frag},sprite:{uniforms:Ce([st.sprite,st.fog]),vertexShader:Ft.sprite_vert,fragmentShader:Ft.sprite_frag},background:{uniforms:{uvTransform:{value:new Ot},t2D:{value:null},backgroundIntensity:{value:1}},vertexShader:Ft.background_vert,fragmentShader:Ft.background_frag},backgroundCube:{uniforms:{envMap:{value:null},flipEnvMap:{value:-1},backgroundBlurriness:{value:0},backgroundIntensity:{value:1},backgroundRotation:{value:new Ot}},vertexShader:Ft.backgroundCube_vert,fragmentShader:Ft.backgroundCube_frag},cube:{uniforms:{tCube:{value:null},tFlip:{value:-1},opacity:{value:1}},vertexShader:Ft.cube_vert,fragmentShader:Ft.cube_frag},equirect:{uniforms:{tEquirect:{value:null}},vertexShader:Ft.equirect_vert,fragmentShader:Ft.equirect_frag},distanceRGBA:{uniforms:Ce([st.common,st.displacementmap,{referencePosition:{value:new R},nearDistance:{value:1},farDistance:{value:1e3}}]),vertexShader:Ft.distanceRGBA_vert,fragmentShader:Ft.distanceRGBA_frag},shadow:{uniforms:Ce([st.lights,st.fog,{color:{value:new Pt(0)},opacity:{value:1}}]),vertexShader:Ft.shadow_vert,fragmentShader:Ft.shadow_frag}};ln.physical={uniforms:Ce([ln.standard.uniforms,{clearcoat:{value:0},clearcoatMap:{value:null},clearcoatMapTransform:{value:new Ot},clearcoatNormalMap:{value:null},clearcoatNormalMapTransform:{value:new Ot},clearcoatNormalScale:{value:new Ht(1,1)},clearcoatRoughness:{value:0},clearcoatRoughnessMap:{value:null},clearcoatRoughnessMapTransform:{value:new Ot},dispersion:{value:0},iridescence:{value:0},iridescenceMap:{value:null},iridescenceMapTransform:{value:new Ot},iridescenceIOR:{value:1.3},iridescenceThicknessMinimum:{value:100},iridescenceThicknessMaximum:{value:400},iridescenceThicknessMap:{value:null},iridescenceThicknessMapTransform:{value:new Ot},sheen:{value:0},sheenColor:{value:new Pt(0)},sheenColorMap:{value:null},sheenColorMapTransform:{value:new Ot},sheenRoughness:{value:1},sheenRoughnessMap:{value:null},sheenRoughnessMapTransform:{value:new Ot},transmission:{value:0},transmissionMap:{value:null},transmissionMapTransform:{value:new Ot},transmissionSamplerSize:{value:new Ht},transmissionSamplerMap:{value:null},thickness:{value:0},thicknessMap:{value:null},thicknessMapTransform:{value:new Ot},attenuationDistance:{value:0},attenuationColor:{value:new Pt(0)},specularColor:{value:new Pt(1,1,1)},specularColorMap:{value:null},specularColorMapTransform:{value:new Ot},specularIntensity:{value:1},specularIntensityMap:{value:null},specularIntensityMapTransform:{value:new Ot},anisotropyVector:{value:new Ht},anisotropyMap:{value:null},anisotropyMapTransform:{value:new Ot}}]),vertexShader:Ft.meshphysical_vert,fragmentShader:Ft.meshphysical_frag};const Ps={r:0,b:0,g:0},zn=new on,Bf=new ee;function kf(i,t,e,n,s,r,a){const o=new Pt(0);let l=r===!0?0:1,h,d,c=null,u=0,f=null;function g(y){let _=y.isScene===!0?y.background:null;return _&&_.isTexture&&(_=(y.backgroundBlurriness>0?e:t).get(_)),_}function v(y){let _=!1;const S=g(y);S===null?p(o,l):S&&S.isColor&&(p(S,1),_=!0);const P=i.xr.getEnvironmentBlendMode();P==="additive"?n.buffers.color.setClear(0,0,0,1,a):P==="alpha-blend"&&n.buffers.color.setClear(0,0,0,0,a),(i.autoClear||_)&&(n.buffers.depth.setTest(!0),n.buffers.depth.setMask(!0),n.buffers.color.setMask(!0),i.clear(i.autoClearColor,i.autoClearDepth,i.autoClearStencil))}function m(y,_){const S=g(_);S&&(S.isCubeTexture||S.mapping===nr)?(d===void 0&&(d=new Ct(new Te(1,1,1),new an({name:"BackgroundCubeMaterial",uniforms:Ii(ln.backgroundCube.uniforms),vertexShader:ln.backgroundCube.vertexShader,fragmentShader:ln.backgroundCube.fragmentShader,side:Pe,depthTest:!1,depthWrite:!1,fog:!1})),d.geometry.deleteAttribute("normal"),d.geometry.deleteAttribute("uv"),d.onBeforeRender=function(P,T,A){this.matrixWorld.copyPosition(A.matrixWorld)},Object.defineProperty(d.material,"envMap",{get:function(){return this.uniforms.envMap.value}}),s.update(d)),zn.copy(_.backgroundRotation),zn.x*=-1,zn.y*=-1,zn.z*=-1,S.isCubeTexture&&S.isRenderTargetTexture===!1&&(zn.y*=-1,zn.z*=-1),d.material.uniforms.envMap.value=S,d.material.uniforms.flipEnvMap.value=S.isCubeTexture&&S.isRenderTargetTexture===!1?-1:1,d.material.uniforms.backgroundBlurriness.value=_.backgroundBlurriness,d.material.uniforms.backgroundIntensity.value=_.backgroundIntensity,d.material.uniforms.backgroundRotation.value.setFromMatrix4(Bf.makeRotationFromEuler(zn)),d.material.toneMapped=Jt.getTransfer(S.colorSpace)!==se,(c!==S||u!==S.version||f!==i.toneMapping)&&(d.material.needsUpdate=!0,c=S,u=S.version,f=i.toneMapping),d.layers.enableAll(),y.unshift(d,d.geometry,d.material,0,0,null)):S&&S.isTexture&&(h===void 0&&(h=new Ct(new Qn(2,2),new an({name:"BackgroundMaterial",uniforms:Ii(ln.background.uniforms),vertexShader:ln.background.vertexShader,fragmentShader:ln.background.fragmentShader,side:hn,depthTest:!1,depthWrite:!1,fog:!1})),h.geometry.deleteAttribute("normal"),Object.defineProperty(h.material,"map",{get:function(){return this.uniforms.t2D.value}}),s.update(h)),h.material.uniforms.t2D.value=S,h.material.uniforms.backgroundIntensity.value=_.backgroundIntensity,h.material.toneMapped=Jt.getTransfer(S.colorSpace)!==se,S.matrixAutoUpdate===!0&&S.updateMatrix(),h.material.uniforms.uvTransform.value.copy(S.matrix),(c!==S||u!==S.version||f!==i.toneMapping)&&(h.material.needsUpdate=!0,c=S,u=S.version,f=i.toneMapping),h.layers.enableAll(),y.unshift(h,h.geometry,h.material,0,0,null))}function p(y,_){y.getRGB(Ps,$l(i)),n.buffers.color.setClear(Ps.r,Ps.g,Ps.b,_,a)}return{getClearColor:function(){return o},setClearColor:function(y,_=1){o.set(y),l=_,p(o,l)},getClearAlpha:function(){return l},setClearAlpha:function(y){l=y,p(o,l)},render:v,addToRenderList:m}}function zf(i,t){const e=i.getParameter(i.MAX_VERTEX_ATTRIBS),n={},s=u(null);let r=s,a=!1;function o(x,E,z,V,K){let G=!1;const I=c(V,z,E);r!==I&&(r=I,h(r.object)),G=f(x,V,z,K),G&&g(x,V,z,K),K!==null&&t.update(K,i.ELEMENT_ARRAY_BUFFER),(G||a)&&(a=!1,S(x,E,z,V),K!==null&&i.bindBuffer(i.ELEMENT_ARRAY_BUFFER,t.get(K).buffer))}function l(){return i.createVertexArray()}function h(x){return i.bindVertexArray(x)}function d(x){return i.deleteVertexArray(x)}function c(x,E,z){const V=z.wireframe===!0;let K=n[x.id];K===void 0&&(K={},n[x.id]=K);let G=K[E.id];G===void 0&&(G={},K[E.id]=G);let I=G[V];return I===void 0&&(I=u(l()),G[V]=I),I}function u(x){const E=[],z=[],V=[];for(let K=0;K<e;K++)E[K]=0,z[K]=0,V[K]=0;return{geometry:null,program:null,wireframe:!1,newAttributes:E,enabledAttributes:z,attributeDivisors:V,object:x,attributes:{},index:null}}function f(x,E,z,V){const K=r.attributes,G=E.attributes;let I=0;const F=z.getAttributes();for(const O in F)if(F[O].location>=0){const nt=K[O];let rt=G[O];if(rt===void 0&&(O==="instanceMatrix"&&x.instanceMatrix&&(rt=x.instanceMatrix),O==="instanceColor"&&x.instanceColor&&(rt=x.instanceColor)),nt===void 0||nt.attribute!==rt||rt&&nt.data!==rt.data)return!0;I++}return r.attributesNum!==I||r.index!==V}function g(x,E,z,V){const K={},G=E.attributes;let I=0;const F=z.getAttributes();for(const O in F)if(F[O].location>=0){let nt=G[O];nt===void 0&&(O==="instanceMatrix"&&x.instanceMatrix&&(nt=x.instanceMatrix),O==="instanceColor"&&x.instanceColor&&(nt=x.instanceColor));const rt={};rt.attribute=nt,nt&&nt.data&&(rt.data=nt.data),K[O]=rt,I++}r.attributes=K,r.attributesNum=I,r.index=V}function v(){const x=r.newAttributes;for(let E=0,z=x.length;E<z;E++)x[E]=0}function m(x){p(x,0)}function p(x,E){const z=r.newAttributes,V=r.enabledAttributes,K=r.attributeDivisors;z[x]=1,V[x]===0&&(i.enableVertexAttribArray(x),V[x]=1),K[x]!==E&&(i.vertexAttribDivisor(x,E),K[x]=E)}function y(){const x=r.newAttributes,E=r.enabledAttributes;for(let z=0,V=E.length;z<V;z++)E[z]!==x[z]&&(i.disableVertexAttribArray(z),E[z]=0)}function _(x,E,z,V,K,G,I){I===!0?i.vertexAttribIPointer(x,E,z,K,G):i.vertexAttribPointer(x,E,z,V,K,G)}function S(x,E,z,V){v();const K=V.attributes,G=z.getAttributes(),I=E.defaultAttributeValues;for(const F in G){const O=G[F];if(O.location>=0){let Q=K[F];if(Q===void 0&&(F==="instanceMatrix"&&x.instanceMatrix&&(Q=x.instanceMatrix),F==="instanceColor"&&x.instanceColor&&(Q=x.instanceColor)),Q!==void 0){const nt=Q.normalized,rt=Q.itemSize,ht=t.get(Q);if(ht===void 0)continue;const ot=ht.buffer,W=ht.type,J=ht.bytesPerElement,it=W===i.INT||W===i.UNSIGNED_INT||Q.gpuType===Fa;if(Q.isInterleavedBufferAttribute){const pt=Q.data,mt=pt.stride,Tt=Q.offset;if(pt.isInstancedInterleavedBuffer){for(let kt=0;kt<O.locationSize;kt++)p(O.location+kt,pt.meshPerAttribute);x.isInstancedMesh!==!0&&V._maxInstanceCount===void 0&&(V._maxInstanceCount=pt.meshPerAttribute*pt.count)}else for(let kt=0;kt<O.locationSize;kt++)m(O.location+kt);i.bindBuffer(i.ARRAY_BUFFER,ot);for(let kt=0;kt<O.locationSize;kt++)_(O.location+kt,rt/O.locationSize,W,nt,mt*J,(Tt+rt/O.locationSize*kt)*J,it)}else{if(Q.isInstancedBufferAttribute){for(let pt=0;pt<O.locationSize;pt++)p(O.location+pt,Q.meshPerAttribute);x.isInstancedMesh!==!0&&V._maxInstanceCount===void 0&&(V._maxInstanceCount=Q.meshPerAttribute*Q.count)}else for(let pt=0;pt<O.locationSize;pt++)m(O.location+pt);i.bindBuffer(i.ARRAY_BUFFER,ot);for(let pt=0;pt<O.locationSize;pt++)_(O.location+pt,rt/O.locationSize,W,nt,rt*J,rt/O.locationSize*pt*J,it)}}else if(I!==void 0){const nt=I[F];if(nt!==void 0)switch(nt.length){case 2:i.vertexAttrib2fv(O.location,nt);break;case 3:i.vertexAttrib3fv(O.location,nt);break;case 4:i.vertexAttrib4fv(O.location,nt);break;default:i.vertexAttrib1fv(O.location,nt)}}}}y()}function P(){L();for(const x in n){const E=n[x];for(const z in E){const V=E[z];for(const K in V)d(V[K].object),delete V[K];delete E[z]}delete n[x]}}function T(x){if(n[x.id]===void 0)return;const E=n[x.id];for(const z in E){const V=E[z];for(const K in V)d(V[K].object),delete V[K];delete E[z]}delete n[x.id]}function A(x){for(const E in n){const z=n[E];if(z[x.id]===void 0)continue;const V=z[x.id];for(const K in V)d(V[K].object),delete V[K];delete z[x.id]}}function L(){q(),a=!0,r!==s&&(r=s,h(r.object))}function q(){s.geometry=null,s.program=null,s.wireframe=!1}return{setup:o,reset:L,resetDefaultState:q,dispose:P,releaseStatesOfGeometry:T,releaseStatesOfProgram:A,initAttributes:v,enableAttribute:m,disableUnusedAttributes:y}}function Hf(i,t,e){let n;function s(h){n=h}function r(h,d){i.drawArrays(n,h,d),e.update(d,n,1)}function a(h,d,c){c!==0&&(i.drawArraysInstanced(n,h,d,c),e.update(d,n,c))}function o(h,d,c){if(c===0)return;t.get("WEBGL_multi_draw").multiDrawArraysWEBGL(n,h,0,d,0,c);let f=0;for(let g=0;g<c;g++)f+=d[g];e.update(f,n,1)}function l(h,d,c,u){if(c===0)return;const f=t.get("WEBGL_multi_draw");if(f===null)for(let g=0;g<h.length;g++)a(h[g],d[g],u[g]);else{f.multiDrawArraysInstancedWEBGL(n,h,0,d,0,u,0,c);let g=0;for(let v=0;v<c;v++)g+=d[v];for(let v=0;v<u.length;v++)e.update(g,n,u[v])}}this.setMode=s,this.render=r,this.renderInstances=a,this.renderMultiDraw=o,this.renderMultiDrawInstances=l}function Gf(i,t,e,n){let s;function r(){if(s!==void 0)return s;if(t.has("EXT_texture_filter_anisotropic")===!0){const A=t.get("EXT_texture_filter_anisotropic");s=i.getParameter(A.MAX_TEXTURE_MAX_ANISOTROPY_EXT)}else s=0;return s}function a(A){return!(A!==rn&&n.convert(A)!==i.getParameter(i.IMPLEMENTATION_COLOR_READ_FORMAT))}function o(A){const L=A===os&&(t.has("EXT_color_buffer_half_float")||t.has("EXT_color_buffer_float"));return!(A!==Mn&&n.convert(A)!==i.getParameter(i.IMPLEMENTATION_COLOR_READ_TYPE)&&A!==cn&&!L)}function l(A){if(A==="highp"){if(i.getShaderPrecisionFormat(i.VERTEX_SHADER,i.HIGH_FLOAT).precision>0&&i.getShaderPrecisionFormat(i.FRAGMENT_SHADER,i.HIGH_FLOAT).precision>0)return"highp";A="mediump"}return A==="mediump"&&i.getShaderPrecisionFormat(i.VERTEX_SHADER,i.MEDIUM_FLOAT).precision>0&&i.getShaderPrecisionFormat(i.FRAGMENT_SHADER,i.MEDIUM_FLOAT).precision>0?"mediump":"lowp"}let h=e.precision!==void 0?e.precision:"highp";const d=l(h);d!==h&&(console.warn("THREE.WebGLRenderer:",h,"not supported, using",d,"instead."),h=d);const c=e.logarithmicDepthBuffer===!0,u=e.reverseDepthBuffer===!0&&t.has("EXT_clip_control");if(u===!0){const A=t.get("EXT_clip_control");A.clipControlEXT(A.LOWER_LEFT_EXT,A.ZERO_TO_ONE_EXT)}const f=i.getParameter(i.MAX_TEXTURE_IMAGE_UNITS),g=i.getParameter(i.MAX_VERTEX_TEXTURE_IMAGE_UNITS),v=i.getParameter(i.MAX_TEXTURE_SIZE),m=i.getParameter(i.MAX_CUBE_MAP_TEXTURE_SIZE),p=i.getParameter(i.MAX_VERTEX_ATTRIBS),y=i.getParameter(i.MAX_VERTEX_UNIFORM_VECTORS),_=i.getParameter(i.MAX_VARYING_VECTORS),S=i.getParameter(i.MAX_FRAGMENT_UNIFORM_VECTORS),P=g>0,T=i.getParameter(i.MAX_SAMPLES);return{isWebGL2:!0,getMaxAnisotropy:r,getMaxPrecision:l,textureFormatReadable:a,textureTypeReadable:o,precision:h,logarithmicDepthBuffer:c,reverseDepthBuffer:u,maxTextures:f,maxVertexTextures:g,maxTextureSize:v,maxCubemapSize:m,maxAttributes:p,maxVertexUniforms:y,maxVaryings:_,maxFragmentUniforms:S,vertexTextures:P,maxSamples:T}}function Vf(i){const t=this;let e=null,n=0,s=!1,r=!1;const a=new Vn,o=new Ot,l={value:null,needsUpdate:!1};this.uniform=l,this.numPlanes=0,this.numIntersection=0,this.init=function(c,u){const f=c.length!==0||u||n!==0||s;return s=u,n=c.length,f},this.beginShadows=function(){r=!0,d(null)},this.endShadows=function(){r=!1},this.setGlobalState=function(c,u){e=d(c,u,0)},this.setState=function(c,u,f){const g=c.clippingPlanes,v=c.clipIntersection,m=c.clipShadows,p=i.get(c);if(!s||g===null||g.length===0||r&&!m)r?d(null):h();else{const y=r?0:n,_=y*4;let S=p.clippingState||null;l.value=S,S=d(g,u,_,f);for(let P=0;P!==_;++P)S[P]=e[P];p.clippingState=S,this.numIntersection=v?this.numPlanes:0,this.numPlanes+=y}};function h(){l.value!==e&&(l.value=e,l.needsUpdate=n>0),t.numPlanes=n,t.numIntersection=0}function d(c,u,f,g){const v=c!==null?c.length:0;let m=null;if(v!==0){if(m=l.value,g!==!0||m===null){const p=f+v*4,y=u.matrixWorldInverse;o.getNormalMatrix(y),(m===null||m.length<p)&&(m=new Float32Array(p));for(let _=0,S=f;_!==v;++_,S+=4)a.copy(c[_]).applyMatrix4(y,o),a.normal.toArray(m,S),m[S+3]=a.constant}l.value=m,l.needsUpdate=!0}return t.numPlanes=v,t.numIntersection=0,m}}function Wf(i){let t=new WeakMap;function e(a,o){return o===na?a.mapping=Ci:o===ia&&(a.mapping=Pi),a}function n(a){if(a&&a.isTexture){const o=a.mapping;if(o===na||o===ia)if(t.has(a)){const l=t.get(a).texture;return e(l,a.mapping)}else{const l=a.image;if(l&&l.height>0){const h=new tu(l.height);return h.fromEquirectangularTexture(i,a),t.set(a,h),a.addEventListener("dispose",s),e(h.texture,a.mapping)}else return null}}return a}function s(a){const o=a.target;o.removeEventListener("dispose",s);const l=t.get(o);l!==void 0&&(t.delete(o),l.dispose())}function r(){t=new WeakMap}return{get:n,dispose:r}}class ec extends Jl{constructor(t=-1,e=1,n=1,s=-1,r=.1,a=2e3){super(),this.isOrthographicCamera=!0,this.type="OrthographicCamera",this.zoom=1,this.view=null,this.left=t,this.right=e,this.top=n,this.bottom=s,this.near=r,this.far=a,this.updateProjectionMatrix()}copy(t,e){return super.copy(t,e),this.left=t.left,this.right=t.right,this.top=t.top,this.bottom=t.bottom,this.near=t.near,this.far=t.far,this.zoom=t.zoom,this.view=t.view===null?null:Object.assign({},t.view),this}setViewOffset(t,e,n,s,r,a){this.view===null&&(this.view={enabled:!0,fullWidth:1,fullHeight:1,offsetX:0,offsetY:0,width:1,height:1}),this.view.enabled=!0,this.view.fullWidth=t,this.view.fullHeight=e,this.view.offsetX=n,this.view.offsetY=s,this.view.width=r,this.view.height=a,this.updateProjectionMatrix()}clearViewOffset(){this.view!==null&&(this.view.enabled=!1),this.updateProjectionMatrix()}updateProjectionMatrix(){const t=(this.right-this.left)/(2*this.zoom),e=(this.top-this.bottom)/(2*this.zoom),n=(this.right+this.left)/2,s=(this.top+this.bottom)/2;let r=n-t,a=n+t,o=s+e,l=s-e;if(this.view!==null&&this.view.enabled){const h=(this.right-this.left)/this.view.fullWidth/this.zoom,d=(this.top-this.bottom)/this.view.fullHeight/this.zoom;r+=h*this.view.offsetX,a=r+h*this.view.width,o-=d*this.view.offsetY,l=o-d*this.view.height}this.projectionMatrix.makeOrthographic(r,a,o,l,this.near,this.far,this.coordinateSystem),this.projectionMatrixInverse.copy(this.projectionMatrix).invert()}toJSON(t){const e=super.toJSON(t);return e.object.zoom=this.zoom,e.object.left=this.left,e.object.right=this.right,e.object.top=this.top,e.object.bottom=this.bottom,e.object.near=this.near,e.object.far=this.far,this.view!==null&&(e.object.view=Object.assign({},this.view)),e}}const yi=4,Lo=[.125,.215,.35,.446,.526,.582],Kn=20,Ur=new ec,Do=new Pt;let Nr=null,Fr=0,Or=0,Br=!1;const Wn=(1+Math.sqrt(5))/2,mi=1/Wn,Io=[new R(-Wn,mi,0),new R(Wn,mi,0),new R(-mi,0,Wn),new R(mi,0,Wn),new R(0,Wn,-mi),new R(0,Wn,mi),new R(-1,1,-1),new R(1,1,-1),new R(-1,1,1),new R(1,1,1)];class Uo{constructor(t){this._renderer=t,this._pingPongRenderTarget=null,this._lodMax=0,this._cubeSize=0,this._lodPlanes=[],this._sizeLods=[],this._sigmas=[],this._blurMaterial=null,this._cubemapMaterial=null,this._equirectMaterial=null,this._compileMaterial(this._blurMaterial)}fromScene(t,e=0,n=.1,s=100){Nr=this._renderer.getRenderTarget(),Fr=this._renderer.getActiveCubeFace(),Or=this._renderer.getActiveMipmapLevel(),Br=this._renderer.xr.enabled,this._renderer.xr.enabled=!1,this._setSize(256);const r=this._allocateTargets();return r.depthBuffer=!0,this._sceneToCubeUV(t,n,s,r),e>0&&this._blur(r,0,0,e),this._applyPMREM(r),this._cleanup(r),r}fromEquirectangular(t,e=null){return this._fromTexture(t,e)}fromCubemap(t,e=null){return this._fromTexture(t,e)}compileCubemapShader(){this._cubemapMaterial===null&&(this._cubemapMaterial=Oo(),this._compileMaterial(this._cubemapMaterial))}compileEquirectangularShader(){this._equirectMaterial===null&&(this._equirectMaterial=Fo(),this._compileMaterial(this._equirectMaterial))}dispose(){this._dispose(),this._cubemapMaterial!==null&&this._cubemapMaterial.dispose(),this._equirectMaterial!==null&&this._equirectMaterial.dispose()}_setSize(t){this._lodMax=Math.floor(Math.log2(t)),this._cubeSize=Math.pow(2,this._lodMax)}_dispose(){this._blurMaterial!==null&&this._blurMaterial.dispose(),this._pingPongRenderTarget!==null&&this._pingPongRenderTarget.dispose();for(let t=0;t<this._lodPlanes.length;t++)this._lodPlanes[t].dispose()}_cleanup(t){this._renderer.setRenderTarget(Nr,Fr,Or),this._renderer.xr.enabled=Br,t.scissorTest=!1,Ls(t,0,0,t.width,t.height)}_fromTexture(t,e){t.mapping===Ci||t.mapping===Pi?this._setSize(t.image.length===0?16:t.image[0].width||t.image[0].image.width):this._setSize(t.image.width/4),Nr=this._renderer.getRenderTarget(),Fr=this._renderer.getActiveCubeFace(),Or=this._renderer.getActiveMipmapLevel(),Br=this._renderer.xr.enabled,this._renderer.xr.enabled=!1;const n=e||this._allocateTargets();return this._textureToCubeUV(t,n),this._applyPMREM(n),this._cleanup(n),n}_allocateTargets(){const t=3*Math.max(this._cubeSize,112),e=4*this._cubeSize,n={magFilter:We,minFilter:We,generateMipmaps:!1,type:os,format:rn,colorSpace:In,depthBuffer:!1},s=No(t,e,n);if(this._pingPongRenderTarget===null||this._pingPongRenderTarget.width!==t||this._pingPongRenderTarget.height!==e){this._pingPongRenderTarget!==null&&this._dispose(),this._pingPongRenderTarget=No(t,e,n);const{_lodMax:r}=this;({sizeLods:this._sizeLods,lodPlanes:this._lodPlanes,sigmas:this._sigmas}=Xf(r)),this._blurMaterial=Yf(r,t,e)}return s}_compileMaterial(t){const e=new Ct(this._lodPlanes[0],t);this._renderer.compile(e,Ur)}_sceneToCubeUV(t,e,n,s){const o=new Ve(90,1,e,n),l=[1,-1,1,1,1,1],h=[1,1,1,-1,-1,-1],d=this._renderer,c=d.autoClear,u=d.toneMapping;d.getClearColor(Do),d.toneMapping=Dn,d.autoClear=!1;const f=new fe({name:"PMREM.Background",side:Pe,depthWrite:!1,depthTest:!1}),g=new Ct(new Te,f);let v=!1;const m=t.background;m?m.isColor&&(f.color.copy(m),t.background=null,v=!0):(f.color.copy(Do),v=!0);for(let p=0;p<6;p++){const y=p%3;y===0?(o.up.set(0,l[p],0),o.lookAt(h[p],0,0)):y===1?(o.up.set(0,0,l[p]),o.lookAt(0,h[p],0)):(o.up.set(0,l[p],0),o.lookAt(0,0,h[p]));const _=this._cubeSize;Ls(s,y*_,p>2?_:0,_,_),d.setRenderTarget(s),v&&d.render(g,o),d.render(t,o)}g.geometry.dispose(),g.material.dispose(),d.toneMapping=u,d.autoClear=c,t.background=m}_textureToCubeUV(t,e){const n=this._renderer,s=t.mapping===Ci||t.mapping===Pi;s?(this._cubemapMaterial===null&&(this._cubemapMaterial=Oo()),this._cubemapMaterial.uniforms.flipEnvMap.value=t.isRenderTargetTexture===!1?-1:1):this._equirectMaterial===null&&(this._equirectMaterial=Fo());const r=s?this._cubemapMaterial:this._equirectMaterial,a=new Ct(this._lodPlanes[0],r),o=r.uniforms;o.envMap.value=t;const l=this._cubeSize;Ls(e,0,0,3*l,2*l),n.setRenderTarget(e),n.render(a,Ur)}_applyPMREM(t){const e=this._renderer,n=e.autoClear;e.autoClear=!1;const s=this._lodPlanes.length;for(let r=1;r<s;r++){const a=Math.sqrt(this._sigmas[r]*this._sigmas[r]-this._sigmas[r-1]*this._sigmas[r-1]),o=Io[(s-r-1)%Io.length];this._blur(t,r-1,r,a,o)}e.autoClear=n}_blur(t,e,n,s,r){const a=this._pingPongRenderTarget;this._halfBlur(t,a,e,n,s,"latitudinal",r),this._halfBlur(a,t,n,n,s,"longitudinal",r)}_halfBlur(t,e,n,s,r,a,o){const l=this._renderer,h=this._blurMaterial;a!=="latitudinal"&&a!=="longitudinal"&&console.error("blur direction must be either latitudinal or longitudinal!");const d=3,c=new Ct(this._lodPlanes[s],h),u=h.uniforms,f=this._sizeLods[n]-1,g=isFinite(r)?Math.PI/(2*f):2*Math.PI/(2*Kn-1),v=r/g,m=isFinite(r)?1+Math.floor(d*v):Kn;m>Kn&&console.warn(`sigmaRadians, ${r}, is too large and will clip, as it requested ${m} samples when the maximum is set to ${Kn}`);const p=[];let y=0;for(let A=0;A<Kn;++A){const L=A/v,q=Math.exp(-L*L/2);p.push(q),A===0?y+=q:A<m&&(y+=2*q)}for(let A=0;A<p.length;A++)p[A]=p[A]/y;u.envMap.value=t.texture,u.samples.value=m,u.weights.value=p,u.latitudinal.value=a==="latitudinal",o&&(u.poleAxis.value=o);const{_lodMax:_}=this;u.dTheta.value=g,u.mipInt.value=_-n;const S=this._sizeLods[s],P=3*S*(s>_-yi?s-_+yi:0),T=4*(this._cubeSize-S);Ls(e,P,T,3*S,2*S),l.setRenderTarget(e),l.render(c,Ur)}}function Xf(i){const t=[],e=[],n=[];let s=i;const r=i-yi+1+Lo.length;for(let a=0;a<r;a++){const o=Math.pow(2,s);e.push(o);let l=1/o;a>i-yi?l=Lo[a-i+yi-1]:a===0&&(l=0),n.push(l);const h=1/(o-2),d=-h,c=1+h,u=[d,d,c,d,c,c,d,d,c,c,d,c],f=6,g=6,v=3,m=2,p=1,y=new Float32Array(v*g*f),_=new Float32Array(m*g*f),S=new Float32Array(p*g*f);for(let T=0;T<f;T++){const A=T%3*2/3-1,L=T>2?0:-1,q=[A,L,0,A+2/3,L,0,A+2/3,L+1,0,A,L,0,A+2/3,L+1,0,A,L+1,0];y.set(q,v*g*T),_.set(u,m*g*T);const x=[T,T,T,T,T,T];S.set(x,p*g*T)}const P=new Le;P.setAttribute("position",new Xe(y,v)),P.setAttribute("uv",new Xe(_,m)),P.setAttribute("faceIndex",new Xe(S,p)),t.push(P),s>yi&&s--}return{lodPlanes:t,sizeLods:e,sigmas:n}}function No(i,t,e){const n=new $n(i,t,e);return n.texture.mapping=nr,n.texture.name="PMREM.cubeUv",n.scissorTest=!0,n}function Ls(i,t,e,n,s){i.viewport.set(t,e,n,s),i.scissor.set(t,e,n,s)}function Yf(i,t,e){const n=new Float32Array(Kn),s=new R(0,1,0);return new an({name:"SphericalGaussianBlur",defines:{n:Kn,CUBEUV_TEXEL_WIDTH:1/t,CUBEUV_TEXEL_HEIGHT:1/e,CUBEUV_MAX_MIP:`${i}.0`},uniforms:{envMap:{value:null},samples:{value:1},weights:{value:n},latitudinal:{value:!1},dTheta:{value:0},mipInt:{value:0},poleAxis:{value:s}},vertexShader:Ka(),fragmentShader:`

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
		`,blending:Ln,depthTest:!1,depthWrite:!1})}function Fo(){return new an({name:"EquirectangularToCubeUV",uniforms:{envMap:{value:null}},vertexShader:Ka(),fragmentShader:`

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
		`,blending:Ln,depthTest:!1,depthWrite:!1})}function Oo(){return new an({name:"CubemapToCubeUV",uniforms:{envMap:{value:null},flipEnvMap:{value:-1}},vertexShader:Ka(),fragmentShader:`

			precision mediump float;
			precision mediump int;

			uniform float flipEnvMap;

			varying vec3 vOutputDirection;

			uniform samplerCube envMap;

			void main() {

				gl_FragColor = textureCube( envMap, vec3( flipEnvMap * vOutputDirection.x, vOutputDirection.yz ) );

			}
		`,blending:Ln,depthTest:!1,depthWrite:!1})}function Ka(){return`

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
	`}function qf(i){let t=new WeakMap,e=null;function n(o){if(o&&o.isTexture){const l=o.mapping,h=l===na||l===ia,d=l===Ci||l===Pi;if(h||d){let c=t.get(o);const u=c!==void 0?c.texture.pmremVersion:0;if(o.isRenderTargetTexture&&o.pmremVersion!==u)return e===null&&(e=new Uo(i)),c=h?e.fromEquirectangular(o,c):e.fromCubemap(o,c),c.texture.pmremVersion=o.pmremVersion,t.set(o,c),c.texture;if(c!==void 0)return c.texture;{const f=o.image;return h&&f&&f.height>0||d&&f&&s(f)?(e===null&&(e=new Uo(i)),c=h?e.fromEquirectangular(o):e.fromCubemap(o),c.texture.pmremVersion=o.pmremVersion,t.set(o,c),o.addEventListener("dispose",r),c.texture):null}}}return o}function s(o){let l=0;const h=6;for(let d=0;d<h;d++)o[d]!==void 0&&l++;return l===h}function r(o){const l=o.target;l.removeEventListener("dispose",r);const h=t.get(l);h!==void 0&&(t.delete(l),h.dispose())}function a(){t=new WeakMap,e!==null&&(e.dispose(),e=null)}return{get:n,dispose:a}}function Kf(i){const t={};function e(n){if(t[n]!==void 0)return t[n];let s;switch(n){case"WEBGL_depth_texture":s=i.getExtension("WEBGL_depth_texture")||i.getExtension("MOZ_WEBGL_depth_texture")||i.getExtension("WEBKIT_WEBGL_depth_texture");break;case"EXT_texture_filter_anisotropic":s=i.getExtension("EXT_texture_filter_anisotropic")||i.getExtension("MOZ_EXT_texture_filter_anisotropic")||i.getExtension("WEBKIT_EXT_texture_filter_anisotropic");break;case"WEBGL_compressed_texture_s3tc":s=i.getExtension("WEBGL_compressed_texture_s3tc")||i.getExtension("MOZ_WEBGL_compressed_texture_s3tc")||i.getExtension("WEBKIT_WEBGL_compressed_texture_s3tc");break;case"WEBGL_compressed_texture_pvrtc":s=i.getExtension("WEBGL_compressed_texture_pvrtc")||i.getExtension("WEBKIT_WEBGL_compressed_texture_pvrtc");break;default:s=i.getExtension(n)}return t[n]=s,s}return{has:function(n){return e(n)!==null},init:function(){e("EXT_color_buffer_float"),e("WEBGL_clip_cull_distance"),e("OES_texture_float_linear"),e("EXT_color_buffer_half_float"),e("WEBGL_multisampled_render_to_texture"),e("WEBGL_render_shared_exponent")},get:function(n){const s=e(n);return s===null&&Xs("THREE.WebGLRenderer: "+n+" extension not supported."),s}}}function jf(i,t,e,n){const s={},r=new WeakMap;function a(c){const u=c.target;u.index!==null&&t.remove(u.index);for(const g in u.attributes)t.remove(u.attributes[g]);for(const g in u.morphAttributes){const v=u.morphAttributes[g];for(let m=0,p=v.length;m<p;m++)t.remove(v[m])}u.removeEventListener("dispose",a),delete s[u.id];const f=r.get(u);f&&(t.remove(f),r.delete(u)),n.releaseStatesOfGeometry(u),u.isInstancedBufferGeometry===!0&&delete u._maxInstanceCount,e.memory.geometries--}function o(c,u){return s[u.id]===!0||(u.addEventListener("dispose",a),s[u.id]=!0,e.memory.geometries++),u}function l(c){const u=c.attributes;for(const g in u)t.update(u[g],i.ARRAY_BUFFER);const f=c.morphAttributes;for(const g in f){const v=f[g];for(let m=0,p=v.length;m<p;m++)t.update(v[m],i.ARRAY_BUFFER)}}function h(c){const u=[],f=c.index,g=c.attributes.position;let v=0;if(f!==null){const y=f.array;v=f.version;for(let _=0,S=y.length;_<S;_+=3){const P=y[_+0],T=y[_+1],A=y[_+2];u.push(P,T,T,A,A,P)}}else if(g!==void 0){const y=g.array;v=g.version;for(let _=0,S=y.length/3-1;_<S;_+=3){const P=_+0,T=_+1,A=_+2;u.push(P,T,T,A,A,P)}}else return;const m=new(Xl(u)?Zl:jl)(u,1);m.version=v;const p=r.get(c);p&&t.remove(p),r.set(c,m)}function d(c){const u=r.get(c);if(u){const f=c.index;f!==null&&u.version<f.version&&h(c)}else h(c);return r.get(c)}return{get:o,update:l,getWireframeAttribute:d}}function Zf(i,t,e){let n;function s(u){n=u}let r,a;function o(u){r=u.type,a=u.bytesPerElement}function l(u,f){i.drawElements(n,f,r,u*a),e.update(f,n,1)}function h(u,f,g){g!==0&&(i.drawElementsInstanced(n,f,r,u*a,g),e.update(f,n,g))}function d(u,f,g){if(g===0)return;t.get("WEBGL_multi_draw").multiDrawElementsWEBGL(n,f,0,r,u,0,g);let m=0;for(let p=0;p<g;p++)m+=f[p];e.update(m,n,1)}function c(u,f,g,v){if(g===0)return;const m=t.get("WEBGL_multi_draw");if(m===null)for(let p=0;p<u.length;p++)h(u[p]/a,f[p],v[p]);else{m.multiDrawElementsInstancedWEBGL(n,f,0,r,u,0,v,0,g);let p=0;for(let y=0;y<g;y++)p+=f[y];for(let y=0;y<v.length;y++)e.update(p,n,v[y])}}this.setMode=s,this.setIndex=o,this.render=l,this.renderInstances=h,this.renderMultiDraw=d,this.renderMultiDrawInstances=c}function $f(i){const t={geometries:0,textures:0},e={frame:0,calls:0,triangles:0,points:0,lines:0};function n(r,a,o){switch(e.calls++,a){case i.TRIANGLES:e.triangles+=o*(r/3);break;case i.LINES:e.lines+=o*(r/2);break;case i.LINE_STRIP:e.lines+=o*(r-1);break;case i.LINE_LOOP:e.lines+=o*r;break;case i.POINTS:e.points+=o*r;break;default:console.error("THREE.WebGLInfo: Unknown draw mode:",a);break}}function s(){e.calls=0,e.triangles=0,e.points=0,e.lines=0}return{memory:t,render:e,programs:null,autoReset:!0,reset:s,update:n}}function Jf(i,t,e){const n=new WeakMap,s=new te;function r(a,o,l){const h=a.morphTargetInfluences,d=o.morphAttributes.position||o.morphAttributes.normal||o.morphAttributes.color,c=d!==void 0?d.length:0;let u=n.get(o);if(u===void 0||u.count!==c){let x=function(){L.dispose(),n.delete(o),o.removeEventListener("dispose",x)};var f=x;u!==void 0&&u.texture.dispose();const g=o.morphAttributes.position!==void 0,v=o.morphAttributes.normal!==void 0,m=o.morphAttributes.color!==void 0,p=o.morphAttributes.position||[],y=o.morphAttributes.normal||[],_=o.morphAttributes.color||[];let S=0;g===!0&&(S=1),v===!0&&(S=2),m===!0&&(S=3);let P=o.attributes.position.count*S,T=1;P>t.maxTextureSize&&(T=Math.ceil(P/t.maxTextureSize),P=t.maxTextureSize);const A=new Float32Array(P*T*4*c),L=new ql(A,P,T,c);L.type=cn,L.needsUpdate=!0;const q=S*4;for(let E=0;E<c;E++){const z=p[E],V=y[E],K=_[E],G=P*T*4*E;for(let I=0;I<z.count;I++){const F=I*q;g===!0&&(s.fromBufferAttribute(z,I),A[G+F+0]=s.x,A[G+F+1]=s.y,A[G+F+2]=s.z,A[G+F+3]=0),v===!0&&(s.fromBufferAttribute(V,I),A[G+F+4]=s.x,A[G+F+5]=s.y,A[G+F+6]=s.z,A[G+F+7]=0),m===!0&&(s.fromBufferAttribute(K,I),A[G+F+8]=s.x,A[G+F+9]=s.y,A[G+F+10]=s.z,A[G+F+11]=K.itemSize===4?s.w:1)}}u={count:c,texture:L,size:new Ht(P,T)},n.set(o,u),o.addEventListener("dispose",x)}if(a.isInstancedMesh===!0&&a.morphTexture!==null)l.getUniforms().setValue(i,"morphTexture",a.morphTexture,e);else{let g=0;for(let m=0;m<h.length;m++)g+=h[m];const v=o.morphTargetsRelative?1:1-g;l.getUniforms().setValue(i,"morphTargetBaseInfluence",v),l.getUniforms().setValue(i,"morphTargetInfluences",h)}l.getUniforms().setValue(i,"morphTargetsTexture",u.texture,e),l.getUniforms().setValue(i,"morphTargetsTextureSize",u.size)}return{update:r}}function Qf(i,t,e,n){let s=new WeakMap;function r(l){const h=n.render.frame,d=l.geometry,c=t.get(l,d);if(s.get(c)!==h&&(t.update(c),s.set(c,h)),l.isInstancedMesh&&(l.hasEventListener("dispose",o)===!1&&l.addEventListener("dispose",o),s.get(l)!==h&&(e.update(l.instanceMatrix,i.ARRAY_BUFFER),l.instanceColor!==null&&e.update(l.instanceColor,i.ARRAY_BUFFER),s.set(l,h))),l.isSkinnedMesh){const u=l.skeleton;s.get(u)!==h&&(u.update(),s.set(u,h))}return c}function a(){s=new WeakMap}function o(l){const h=l.target;h.removeEventListener("dispose",o),e.remove(h.instanceMatrix),h.instanceColor!==null&&e.remove(h.instanceColor)}return{update:r,dispose:a}}class nc extends be{constructor(t,e,n,s,r,a,o,l,h,d=bi){if(d!==bi&&d!==Di)throw new Error("DepthTexture format must be either THREE.DepthFormat or THREE.DepthStencilFormat");n===void 0&&d===bi&&(n=Zn),n===void 0&&d===Di&&(n=Li),super(null,s,r,a,o,l,d,n,h),this.isDepthTexture=!0,this.image={width:t,height:e},this.magFilter=o!==void 0?o:Ue,this.minFilter=l!==void 0?l:Ue,this.flipY=!1,this.generateMipmaps=!1,this.compareFunction=null}copy(t){return super.copy(t),this.compareFunction=t.compareFunction,this}toJSON(t){const e=super.toJSON(t);return this.compareFunction!==null&&(e.compareFunction=this.compareFunction),e}}const ic=new be,Bo=new nc(1,1),sc=new ql,rc=new Bh,ac=new Ql,ko=[],zo=[],Ho=new Float32Array(16),Go=new Float32Array(9),Vo=new Float32Array(4);function ki(i,t,e){const n=i[0];if(n<=0||n>0)return i;const s=t*e;let r=ko[s];if(r===void 0&&(r=new Float32Array(s),ko[s]=r),t!==0){n.toArray(r,0);for(let a=1,o=0;a!==t;++a)o+=e,i[a].toArray(r,o)}return r}function ge(i,t){if(i.length!==t.length)return!1;for(let e=0,n=i.length;e<n;e++)if(i[e]!==t[e])return!1;return!0}function _e(i,t){for(let e=0,n=t.length;e<n;e++)i[e]=t[e]}function sr(i,t){let e=zo[t];e===void 0&&(e=new Int32Array(t),zo[t]=e);for(let n=0;n!==t;++n)e[n]=i.allocateTextureUnit();return e}function tp(i,t){const e=this.cache;e[0]!==t&&(i.uniform1f(this.addr,t),e[0]=t)}function ep(i,t){const e=this.cache;if(t.x!==void 0)(e[0]!==t.x||e[1]!==t.y)&&(i.uniform2f(this.addr,t.x,t.y),e[0]=t.x,e[1]=t.y);else{if(ge(e,t))return;i.uniform2fv(this.addr,t),_e(e,t)}}function np(i,t){const e=this.cache;if(t.x!==void 0)(e[0]!==t.x||e[1]!==t.y||e[2]!==t.z)&&(i.uniform3f(this.addr,t.x,t.y,t.z),e[0]=t.x,e[1]=t.y,e[2]=t.z);else if(t.r!==void 0)(e[0]!==t.r||e[1]!==t.g||e[2]!==t.b)&&(i.uniform3f(this.addr,t.r,t.g,t.b),e[0]=t.r,e[1]=t.g,e[2]=t.b);else{if(ge(e,t))return;i.uniform3fv(this.addr,t),_e(e,t)}}function ip(i,t){const e=this.cache;if(t.x!==void 0)(e[0]!==t.x||e[1]!==t.y||e[2]!==t.z||e[3]!==t.w)&&(i.uniform4f(this.addr,t.x,t.y,t.z,t.w),e[0]=t.x,e[1]=t.y,e[2]=t.z,e[3]=t.w);else{if(ge(e,t))return;i.uniform4fv(this.addr,t),_e(e,t)}}function sp(i,t){const e=this.cache,n=t.elements;if(n===void 0){if(ge(e,t))return;i.uniformMatrix2fv(this.addr,!1,t),_e(e,t)}else{if(ge(e,n))return;Vo.set(n),i.uniformMatrix2fv(this.addr,!1,Vo),_e(e,n)}}function rp(i,t){const e=this.cache,n=t.elements;if(n===void 0){if(ge(e,t))return;i.uniformMatrix3fv(this.addr,!1,t),_e(e,t)}else{if(ge(e,n))return;Go.set(n),i.uniformMatrix3fv(this.addr,!1,Go),_e(e,n)}}function ap(i,t){const e=this.cache,n=t.elements;if(n===void 0){if(ge(e,t))return;i.uniformMatrix4fv(this.addr,!1,t),_e(e,t)}else{if(ge(e,n))return;Ho.set(n),i.uniformMatrix4fv(this.addr,!1,Ho),_e(e,n)}}function op(i,t){const e=this.cache;e[0]!==t&&(i.uniform1i(this.addr,t),e[0]=t)}function lp(i,t){const e=this.cache;if(t.x!==void 0)(e[0]!==t.x||e[1]!==t.y)&&(i.uniform2i(this.addr,t.x,t.y),e[0]=t.x,e[1]=t.y);else{if(ge(e,t))return;i.uniform2iv(this.addr,t),_e(e,t)}}function cp(i,t){const e=this.cache;if(t.x!==void 0)(e[0]!==t.x||e[1]!==t.y||e[2]!==t.z)&&(i.uniform3i(this.addr,t.x,t.y,t.z),e[0]=t.x,e[1]=t.y,e[2]=t.z);else{if(ge(e,t))return;i.uniform3iv(this.addr,t),_e(e,t)}}function hp(i,t){const e=this.cache;if(t.x!==void 0)(e[0]!==t.x||e[1]!==t.y||e[2]!==t.z||e[3]!==t.w)&&(i.uniform4i(this.addr,t.x,t.y,t.z,t.w),e[0]=t.x,e[1]=t.y,e[2]=t.z,e[3]=t.w);else{if(ge(e,t))return;i.uniform4iv(this.addr,t),_e(e,t)}}function up(i,t){const e=this.cache;e[0]!==t&&(i.uniform1ui(this.addr,t),e[0]=t)}function dp(i,t){const e=this.cache;if(t.x!==void 0)(e[0]!==t.x||e[1]!==t.y)&&(i.uniform2ui(this.addr,t.x,t.y),e[0]=t.x,e[1]=t.y);else{if(ge(e,t))return;i.uniform2uiv(this.addr,t),_e(e,t)}}function fp(i,t){const e=this.cache;if(t.x!==void 0)(e[0]!==t.x||e[1]!==t.y||e[2]!==t.z)&&(i.uniform3ui(this.addr,t.x,t.y,t.z),e[0]=t.x,e[1]=t.y,e[2]=t.z);else{if(ge(e,t))return;i.uniform3uiv(this.addr,t),_e(e,t)}}function pp(i,t){const e=this.cache;if(t.x!==void 0)(e[0]!==t.x||e[1]!==t.y||e[2]!==t.z||e[3]!==t.w)&&(i.uniform4ui(this.addr,t.x,t.y,t.z,t.w),e[0]=t.x,e[1]=t.y,e[2]=t.z,e[3]=t.w);else{if(ge(e,t))return;i.uniform4uiv(this.addr,t),_e(e,t)}}function mp(i,t,e){const n=this.cache,s=e.allocateTextureUnit();n[0]!==s&&(i.uniform1i(this.addr,s),n[0]=s);let r;this.type===i.SAMPLER_2D_SHADOW?(Bo.compareFunction=Wl,r=Bo):r=ic,e.setTexture2D(t||r,s)}function gp(i,t,e){const n=this.cache,s=e.allocateTextureUnit();n[0]!==s&&(i.uniform1i(this.addr,s),n[0]=s),e.setTexture3D(t||rc,s)}function _p(i,t,e){const n=this.cache,s=e.allocateTextureUnit();n[0]!==s&&(i.uniform1i(this.addr,s),n[0]=s),e.setTextureCube(t||ac,s)}function xp(i,t,e){const n=this.cache,s=e.allocateTextureUnit();n[0]!==s&&(i.uniform1i(this.addr,s),n[0]=s),e.setTexture2DArray(t||sc,s)}function vp(i){switch(i){case 5126:return tp;case 35664:return ep;case 35665:return np;case 35666:return ip;case 35674:return sp;case 35675:return rp;case 35676:return ap;case 5124:case 35670:return op;case 35667:case 35671:return lp;case 35668:case 35672:return cp;case 35669:case 35673:return hp;case 5125:return up;case 36294:return dp;case 36295:return fp;case 36296:return pp;case 35678:case 36198:case 36298:case 36306:case 35682:return mp;case 35679:case 36299:case 36307:return gp;case 35680:case 36300:case 36308:case 36293:return _p;case 36289:case 36303:case 36311:case 36292:return xp}}function Mp(i,t){i.uniform1fv(this.addr,t)}function yp(i,t){const e=ki(t,this.size,2);i.uniform2fv(this.addr,e)}function Sp(i,t){const e=ki(t,this.size,3);i.uniform3fv(this.addr,e)}function wp(i,t){const e=ki(t,this.size,4);i.uniform4fv(this.addr,e)}function Ep(i,t){const e=ki(t,this.size,4);i.uniformMatrix2fv(this.addr,!1,e)}function bp(i,t){const e=ki(t,this.size,9);i.uniformMatrix3fv(this.addr,!1,e)}function Tp(i,t){const e=ki(t,this.size,16);i.uniformMatrix4fv(this.addr,!1,e)}function Ap(i,t){i.uniform1iv(this.addr,t)}function Rp(i,t){i.uniform2iv(this.addr,t)}function Cp(i,t){i.uniform3iv(this.addr,t)}function Pp(i,t){i.uniform4iv(this.addr,t)}function Lp(i,t){i.uniform1uiv(this.addr,t)}function Dp(i,t){i.uniform2uiv(this.addr,t)}function Ip(i,t){i.uniform3uiv(this.addr,t)}function Up(i,t){i.uniform4uiv(this.addr,t)}function Np(i,t,e){const n=this.cache,s=t.length,r=sr(e,s);ge(n,r)||(i.uniform1iv(this.addr,r),_e(n,r));for(let a=0;a!==s;++a)e.setTexture2D(t[a]||ic,r[a])}function Fp(i,t,e){const n=this.cache,s=t.length,r=sr(e,s);ge(n,r)||(i.uniform1iv(this.addr,r),_e(n,r));for(let a=0;a!==s;++a)e.setTexture3D(t[a]||rc,r[a])}function Op(i,t,e){const n=this.cache,s=t.length,r=sr(e,s);ge(n,r)||(i.uniform1iv(this.addr,r),_e(n,r));for(let a=0;a!==s;++a)e.setTextureCube(t[a]||ac,r[a])}function Bp(i,t,e){const n=this.cache,s=t.length,r=sr(e,s);ge(n,r)||(i.uniform1iv(this.addr,r),_e(n,r));for(let a=0;a!==s;++a)e.setTexture2DArray(t[a]||sc,r[a])}function kp(i){switch(i){case 5126:return Mp;case 35664:return yp;case 35665:return Sp;case 35666:return wp;case 35674:return Ep;case 35675:return bp;case 35676:return Tp;case 5124:case 35670:return Ap;case 35667:case 35671:return Rp;case 35668:case 35672:return Cp;case 35669:case 35673:return Pp;case 5125:return Lp;case 36294:return Dp;case 36295:return Ip;case 36296:return Up;case 35678:case 36198:case 36298:case 36306:case 35682:return Np;case 35679:case 36299:case 36307:return Fp;case 35680:case 36300:case 36308:case 36293:return Op;case 36289:case 36303:case 36311:case 36292:return Bp}}class zp{constructor(t,e,n){this.id=t,this.addr=n,this.cache=[],this.type=e.type,this.setValue=vp(e.type)}}class Hp{constructor(t,e,n){this.id=t,this.addr=n,this.cache=[],this.type=e.type,this.size=e.size,this.setValue=kp(e.type)}}class Gp{constructor(t){this.id=t,this.seq=[],this.map={}}setValue(t,e,n){const s=this.seq;for(let r=0,a=s.length;r!==a;++r){const o=s[r];o.setValue(t,e[o.id],n)}}}const kr=/(\w+)(\])?(\[|\.)?/g;function Wo(i,t){i.seq.push(t),i.map[t.id]=t}function Vp(i,t,e){const n=i.name,s=n.length;for(kr.lastIndex=0;;){const r=kr.exec(n),a=kr.lastIndex;let o=r[1];const l=r[2]==="]",h=r[3];if(l&&(o=o|0),h===void 0||h==="["&&a+2===s){Wo(e,h===void 0?new zp(o,i,t):new Hp(o,i,t));break}else{let c=e.map[o];c===void 0&&(c=new Gp(o),Wo(e,c)),e=c}}}class Ys{constructor(t,e){this.seq=[],this.map={};const n=t.getProgramParameter(e,t.ACTIVE_UNIFORMS);for(let s=0;s<n;++s){const r=t.getActiveUniform(e,s),a=t.getUniformLocation(e,r.name);Vp(r,a,this)}}setValue(t,e,n,s){const r=this.map[e];r!==void 0&&r.setValue(t,n,s)}setOptional(t,e,n){const s=e[n];s!==void 0&&this.setValue(t,n,s)}static upload(t,e,n,s){for(let r=0,a=e.length;r!==a;++r){const o=e[r],l=n[o.id];l.needsUpdate!==!1&&o.setValue(t,l.value,s)}}static seqWithValue(t,e){const n=[];for(let s=0,r=t.length;s!==r;++s){const a=t[s];a.id in e&&n.push(a)}return n}}function Xo(i,t,e){const n=i.createShader(t);return i.shaderSource(n,e),i.compileShader(n),n}const Wp=37297;let Xp=0;function Yp(i,t){const e=i.split(`
`),n=[],s=Math.max(t-6,0),r=Math.min(t+6,e.length);for(let a=s;a<r;a++){const o=a+1;n.push(`${o===t?">":" "} ${o}: ${e[a]}`)}return n.join(`
`)}function qp(i){const t=Jt.getPrimaries(Jt.workingColorSpace),e=Jt.getPrimaries(i);let n;switch(t===e?n="":t===Zs&&e===js?n="LinearDisplayP3ToLinearSRGB":t===js&&e===Zs&&(n="LinearSRGBToLinearDisplayP3"),i){case In:case ir:return[n,"LinearTransferOETF"];case je:case Va:return[n,"sRGBTransferOETF"];default:return console.warn("THREE.WebGLProgram: Unsupported color space:",i),[n,"LinearTransferOETF"]}}function Yo(i,t,e){const n=i.getShaderParameter(t,i.COMPILE_STATUS),s=i.getShaderInfoLog(t).trim();if(n&&s==="")return"";const r=/ERROR: 0:(\d+)/.exec(s);if(r){const a=parseInt(r[1]);return e.toUpperCase()+`

`+s+`

`+Yp(i.getShaderSource(t),a)}else return s}function Kp(i,t){const e=qp(t);return`vec4 ${i}( vec4 value ) { return ${e[0]}( ${e[1]}( value ) ); }`}function jp(i,t){let e;switch(t){case Kc:e="Linear";break;case jc:e="Reinhard";break;case Zc:e="Cineon";break;case Dl:e="ACESFilmic";break;case Jc:e="AgX";break;case Qc:e="Neutral";break;case $c:e="Custom";break;default:console.warn("THREE.WebGLProgram: Unsupported toneMapping:",t),e="Linear"}return"vec3 "+i+"( vec3 color ) { return "+e+"ToneMapping( color ); }"}const Ds=new R;function Zp(){Jt.getLuminanceCoefficients(Ds);const i=Ds.x.toFixed(4),t=Ds.y.toFixed(4),e=Ds.z.toFixed(4);return["float luminance( const in vec3 rgb ) {",`	const vec3 weights = vec3( ${i}, ${t}, ${e} );`,"	return dot( weights, rgb );","}"].join(`
`)}function $p(i){return[i.extensionClipCullDistance?"#extension GL_ANGLE_clip_cull_distance : require":"",i.extensionMultiDraw?"#extension GL_ANGLE_multi_draw : require":""].filter($i).join(`
`)}function Jp(i){const t=[];for(const e in i){const n=i[e];n!==!1&&t.push("#define "+e+" "+n)}return t.join(`
`)}function Qp(i,t){const e={},n=i.getProgramParameter(t,i.ACTIVE_ATTRIBUTES);for(let s=0;s<n;s++){const r=i.getActiveAttrib(t,s),a=r.name;let o=1;r.type===i.FLOAT_MAT2&&(o=2),r.type===i.FLOAT_MAT3&&(o=3),r.type===i.FLOAT_MAT4&&(o=4),e[a]={type:r.type,location:i.getAttribLocation(t,a),locationSize:o}}return e}function $i(i){return i!==""}function qo(i,t){const e=t.numSpotLightShadows+t.numSpotLightMaps-t.numSpotLightShadowsWithMaps;return i.replace(/NUM_DIR_LIGHTS/g,t.numDirLights).replace(/NUM_SPOT_LIGHTS/g,t.numSpotLights).replace(/NUM_SPOT_LIGHT_MAPS/g,t.numSpotLightMaps).replace(/NUM_SPOT_LIGHT_COORDS/g,e).replace(/NUM_RECT_AREA_LIGHTS/g,t.numRectAreaLights).replace(/NUM_POINT_LIGHTS/g,t.numPointLights).replace(/NUM_HEMI_LIGHTS/g,t.numHemiLights).replace(/NUM_DIR_LIGHT_SHADOWS/g,t.numDirLightShadows).replace(/NUM_SPOT_LIGHT_SHADOWS_WITH_MAPS/g,t.numSpotLightShadowsWithMaps).replace(/NUM_SPOT_LIGHT_SHADOWS/g,t.numSpotLightShadows).replace(/NUM_POINT_LIGHT_SHADOWS/g,t.numPointLightShadows)}function Ko(i,t){return i.replace(/NUM_CLIPPING_PLANES/g,t.numClippingPlanes).replace(/UNION_CLIPPING_PLANES/g,t.numClippingPlanes-t.numClipIntersection)}const tm=/^[ \t]*#include +<([\w\d./]+)>/gm;function La(i){return i.replace(tm,nm)}const em=new Map;function nm(i,t){let e=Ft[t];if(e===void 0){const n=em.get(t);if(n!==void 0)e=Ft[n],console.warn('THREE.WebGLRenderer: Shader chunk "%s" has been deprecated. Use "%s" instead.',t,n);else throw new Error("Can not resolve #include <"+t+">")}return La(e)}const im=/#pragma unroll_loop_start\s+for\s*\(\s*int\s+i\s*=\s*(\d+)\s*;\s*i\s*<\s*(\d+)\s*;\s*i\s*\+\+\s*\)\s*{([\s\S]+?)}\s+#pragma unroll_loop_end/g;function jo(i){return i.replace(im,sm)}function sm(i,t,e,n){let s="";for(let r=parseInt(t);r<parseInt(e);r++)s+=n.replace(/\[\s*i\s*\]/g,"[ "+r+" ]").replace(/UNROLLED_LOOP_INDEX/g,r);return s}function Zo(i){let t=`precision ${i.precision} float;
	precision ${i.precision} int;
	precision ${i.precision} sampler2D;
	precision ${i.precision} samplerCube;
	precision ${i.precision} sampler3D;
	precision ${i.precision} sampler2DArray;
	precision ${i.precision} sampler2DShadow;
	precision ${i.precision} samplerCubeShadow;
	precision ${i.precision} sampler2DArrayShadow;
	precision ${i.precision} isampler2D;
	precision ${i.precision} isampler3D;
	precision ${i.precision} isamplerCube;
	precision ${i.precision} isampler2DArray;
	precision ${i.precision} usampler2D;
	precision ${i.precision} usampler3D;
	precision ${i.precision} usamplerCube;
	precision ${i.precision} usampler2DArray;
	`;return i.precision==="highp"?t+=`
#define HIGH_PRECISION`:i.precision==="mediump"?t+=`
#define MEDIUM_PRECISION`:i.precision==="lowp"&&(t+=`
#define LOW_PRECISION`),t}function rm(i){let t="SHADOWMAP_TYPE_BASIC";return i.shadowMapType===Pl?t="SHADOWMAP_TYPE_PCF":i.shadowMapType===Ac?t="SHADOWMAP_TYPE_PCF_SOFT":i.shadowMapType===_n&&(t="SHADOWMAP_TYPE_VSM"),t}function am(i){let t="ENVMAP_TYPE_CUBE";if(i.envMap)switch(i.envMapMode){case Ci:case Pi:t="ENVMAP_TYPE_CUBE";break;case nr:t="ENVMAP_TYPE_CUBE_UV";break}return t}function om(i){let t="ENVMAP_MODE_REFLECTION";if(i.envMap)switch(i.envMapMode){case Pi:t="ENVMAP_MODE_REFRACTION";break}return t}function lm(i){let t="ENVMAP_BLENDING_NONE";if(i.envMap)switch(i.combine){case Ll:t="ENVMAP_BLENDING_MULTIPLY";break;case Yc:t="ENVMAP_BLENDING_MIX";break;case qc:t="ENVMAP_BLENDING_ADD";break}return t}function cm(i){const t=i.envMapCubeUVHeight;if(t===null)return null;const e=Math.log2(t)-2,n=1/t;return{texelWidth:1/(3*Math.max(Math.pow(2,e),7*16)),texelHeight:n,maxMip:e}}function hm(i,t,e,n){const s=i.getContext(),r=e.defines;let a=e.vertexShader,o=e.fragmentShader;const l=rm(e),h=am(e),d=om(e),c=lm(e),u=cm(e),f=$p(e),g=Jp(r),v=s.createProgram();let m,p,y=e.glslVersion?"#version "+e.glslVersion+`
`:"";e.isRawShaderMaterial?(m=["#define SHADER_TYPE "+e.shaderType,"#define SHADER_NAME "+e.shaderName,g].filter($i).join(`
`),m.length>0&&(m+=`
`),p=["#define SHADER_TYPE "+e.shaderType,"#define SHADER_NAME "+e.shaderName,g].filter($i).join(`
`),p.length>0&&(p+=`
`)):(m=[Zo(e),"#define SHADER_TYPE "+e.shaderType,"#define SHADER_NAME "+e.shaderName,g,e.extensionClipCullDistance?"#define USE_CLIP_DISTANCE":"",e.batching?"#define USE_BATCHING":"",e.batchingColor?"#define USE_BATCHING_COLOR":"",e.instancing?"#define USE_INSTANCING":"",e.instancingColor?"#define USE_INSTANCING_COLOR":"",e.instancingMorph?"#define USE_INSTANCING_MORPH":"",e.useFog&&e.fog?"#define USE_FOG":"",e.useFog&&e.fogExp2?"#define FOG_EXP2":"",e.map?"#define USE_MAP":"",e.envMap?"#define USE_ENVMAP":"",e.envMap?"#define "+d:"",e.lightMap?"#define USE_LIGHTMAP":"",e.aoMap?"#define USE_AOMAP":"",e.bumpMap?"#define USE_BUMPMAP":"",e.normalMap?"#define USE_NORMALMAP":"",e.normalMapObjectSpace?"#define USE_NORMALMAP_OBJECTSPACE":"",e.normalMapTangentSpace?"#define USE_NORMALMAP_TANGENTSPACE":"",e.displacementMap?"#define USE_DISPLACEMENTMAP":"",e.emissiveMap?"#define USE_EMISSIVEMAP":"",e.anisotropy?"#define USE_ANISOTROPY":"",e.anisotropyMap?"#define USE_ANISOTROPYMAP":"",e.clearcoatMap?"#define USE_CLEARCOATMAP":"",e.clearcoatRoughnessMap?"#define USE_CLEARCOAT_ROUGHNESSMAP":"",e.clearcoatNormalMap?"#define USE_CLEARCOAT_NORMALMAP":"",e.iridescenceMap?"#define USE_IRIDESCENCEMAP":"",e.iridescenceThicknessMap?"#define USE_IRIDESCENCE_THICKNESSMAP":"",e.specularMap?"#define USE_SPECULARMAP":"",e.specularColorMap?"#define USE_SPECULAR_COLORMAP":"",e.specularIntensityMap?"#define USE_SPECULAR_INTENSITYMAP":"",e.roughnessMap?"#define USE_ROUGHNESSMAP":"",e.metalnessMap?"#define USE_METALNESSMAP":"",e.alphaMap?"#define USE_ALPHAMAP":"",e.alphaHash?"#define USE_ALPHAHASH":"",e.transmission?"#define USE_TRANSMISSION":"",e.transmissionMap?"#define USE_TRANSMISSIONMAP":"",e.thicknessMap?"#define USE_THICKNESSMAP":"",e.sheenColorMap?"#define USE_SHEEN_COLORMAP":"",e.sheenRoughnessMap?"#define USE_SHEEN_ROUGHNESSMAP":"",e.mapUv?"#define MAP_UV "+e.mapUv:"",e.alphaMapUv?"#define ALPHAMAP_UV "+e.alphaMapUv:"",e.lightMapUv?"#define LIGHTMAP_UV "+e.lightMapUv:"",e.aoMapUv?"#define AOMAP_UV "+e.aoMapUv:"",e.emissiveMapUv?"#define EMISSIVEMAP_UV "+e.emissiveMapUv:"",e.bumpMapUv?"#define BUMPMAP_UV "+e.bumpMapUv:"",e.normalMapUv?"#define NORMALMAP_UV "+e.normalMapUv:"",e.displacementMapUv?"#define DISPLACEMENTMAP_UV "+e.displacementMapUv:"",e.metalnessMapUv?"#define METALNESSMAP_UV "+e.metalnessMapUv:"",e.roughnessMapUv?"#define ROUGHNESSMAP_UV "+e.roughnessMapUv:"",e.anisotropyMapUv?"#define ANISOTROPYMAP_UV "+e.anisotropyMapUv:"",e.clearcoatMapUv?"#define CLEARCOATMAP_UV "+e.clearcoatMapUv:"",e.clearcoatNormalMapUv?"#define CLEARCOAT_NORMALMAP_UV "+e.clearcoatNormalMapUv:"",e.clearcoatRoughnessMapUv?"#define CLEARCOAT_ROUGHNESSMAP_UV "+e.clearcoatRoughnessMapUv:"",e.iridescenceMapUv?"#define IRIDESCENCEMAP_UV "+e.iridescenceMapUv:"",e.iridescenceThicknessMapUv?"#define IRIDESCENCE_THICKNESSMAP_UV "+e.iridescenceThicknessMapUv:"",e.sheenColorMapUv?"#define SHEEN_COLORMAP_UV "+e.sheenColorMapUv:"",e.sheenRoughnessMapUv?"#define SHEEN_ROUGHNESSMAP_UV "+e.sheenRoughnessMapUv:"",e.specularMapUv?"#define SPECULARMAP_UV "+e.specularMapUv:"",e.specularColorMapUv?"#define SPECULAR_COLORMAP_UV "+e.specularColorMapUv:"",e.specularIntensityMapUv?"#define SPECULAR_INTENSITYMAP_UV "+e.specularIntensityMapUv:"",e.transmissionMapUv?"#define TRANSMISSIONMAP_UV "+e.transmissionMapUv:"",e.thicknessMapUv?"#define THICKNESSMAP_UV "+e.thicknessMapUv:"",e.vertexTangents&&e.flatShading===!1?"#define USE_TANGENT":"",e.vertexColors?"#define USE_COLOR":"",e.vertexAlphas?"#define USE_COLOR_ALPHA":"",e.vertexUv1s?"#define USE_UV1":"",e.vertexUv2s?"#define USE_UV2":"",e.vertexUv3s?"#define USE_UV3":"",e.pointsUvs?"#define USE_POINTS_UV":"",e.flatShading?"#define FLAT_SHADED":"",e.skinning?"#define USE_SKINNING":"",e.morphTargets?"#define USE_MORPHTARGETS":"",e.morphNormals&&e.flatShading===!1?"#define USE_MORPHNORMALS":"",e.morphColors?"#define USE_MORPHCOLORS":"",e.morphTargetsCount>0?"#define MORPHTARGETS_TEXTURE_STRIDE "+e.morphTextureStride:"",e.morphTargetsCount>0?"#define MORPHTARGETS_COUNT "+e.morphTargetsCount:"",e.doubleSided?"#define DOUBLE_SIDED":"",e.flipSided?"#define FLIP_SIDED":"",e.shadowMapEnabled?"#define USE_SHADOWMAP":"",e.shadowMapEnabled?"#define "+l:"",e.sizeAttenuation?"#define USE_SIZEATTENUATION":"",e.numLightProbes>0?"#define USE_LIGHT_PROBES":"",e.logarithmicDepthBuffer?"#define USE_LOGDEPTHBUF":"",e.reverseDepthBuffer?"#define USE_REVERSEDEPTHBUF":"","uniform mat4 modelMatrix;","uniform mat4 modelViewMatrix;","uniform mat4 projectionMatrix;","uniform mat4 viewMatrix;","uniform mat3 normalMatrix;","uniform vec3 cameraPosition;","uniform bool isOrthographic;","#ifdef USE_INSTANCING","	attribute mat4 instanceMatrix;","#endif","#ifdef USE_INSTANCING_COLOR","	attribute vec3 instanceColor;","#endif","#ifdef USE_INSTANCING_MORPH","	uniform sampler2D morphTexture;","#endif","attribute vec3 position;","attribute vec3 normal;","attribute vec2 uv;","#ifdef USE_UV1","	attribute vec2 uv1;","#endif","#ifdef USE_UV2","	attribute vec2 uv2;","#endif","#ifdef USE_UV3","	attribute vec2 uv3;","#endif","#ifdef USE_TANGENT","	attribute vec4 tangent;","#endif","#if defined( USE_COLOR_ALPHA )","	attribute vec4 color;","#elif defined( USE_COLOR )","	attribute vec3 color;","#endif","#ifdef USE_SKINNING","	attribute vec4 skinIndex;","	attribute vec4 skinWeight;","#endif",`
`].filter($i).join(`
`),p=[Zo(e),"#define SHADER_TYPE "+e.shaderType,"#define SHADER_NAME "+e.shaderName,g,e.useFog&&e.fog?"#define USE_FOG":"",e.useFog&&e.fogExp2?"#define FOG_EXP2":"",e.alphaToCoverage?"#define ALPHA_TO_COVERAGE":"",e.map?"#define USE_MAP":"",e.matcap?"#define USE_MATCAP":"",e.envMap?"#define USE_ENVMAP":"",e.envMap?"#define "+h:"",e.envMap?"#define "+d:"",e.envMap?"#define "+c:"",u?"#define CUBEUV_TEXEL_WIDTH "+u.texelWidth:"",u?"#define CUBEUV_TEXEL_HEIGHT "+u.texelHeight:"",u?"#define CUBEUV_MAX_MIP "+u.maxMip+".0":"",e.lightMap?"#define USE_LIGHTMAP":"",e.aoMap?"#define USE_AOMAP":"",e.bumpMap?"#define USE_BUMPMAP":"",e.normalMap?"#define USE_NORMALMAP":"",e.normalMapObjectSpace?"#define USE_NORMALMAP_OBJECTSPACE":"",e.normalMapTangentSpace?"#define USE_NORMALMAP_TANGENTSPACE":"",e.emissiveMap?"#define USE_EMISSIVEMAP":"",e.anisotropy?"#define USE_ANISOTROPY":"",e.anisotropyMap?"#define USE_ANISOTROPYMAP":"",e.clearcoat?"#define USE_CLEARCOAT":"",e.clearcoatMap?"#define USE_CLEARCOATMAP":"",e.clearcoatRoughnessMap?"#define USE_CLEARCOAT_ROUGHNESSMAP":"",e.clearcoatNormalMap?"#define USE_CLEARCOAT_NORMALMAP":"",e.dispersion?"#define USE_DISPERSION":"",e.iridescence?"#define USE_IRIDESCENCE":"",e.iridescenceMap?"#define USE_IRIDESCENCEMAP":"",e.iridescenceThicknessMap?"#define USE_IRIDESCENCE_THICKNESSMAP":"",e.specularMap?"#define USE_SPECULARMAP":"",e.specularColorMap?"#define USE_SPECULAR_COLORMAP":"",e.specularIntensityMap?"#define USE_SPECULAR_INTENSITYMAP":"",e.roughnessMap?"#define USE_ROUGHNESSMAP":"",e.metalnessMap?"#define USE_METALNESSMAP":"",e.alphaMap?"#define USE_ALPHAMAP":"",e.alphaTest?"#define USE_ALPHATEST":"",e.alphaHash?"#define USE_ALPHAHASH":"",e.sheen?"#define USE_SHEEN":"",e.sheenColorMap?"#define USE_SHEEN_COLORMAP":"",e.sheenRoughnessMap?"#define USE_SHEEN_ROUGHNESSMAP":"",e.transmission?"#define USE_TRANSMISSION":"",e.transmissionMap?"#define USE_TRANSMISSIONMAP":"",e.thicknessMap?"#define USE_THICKNESSMAP":"",e.vertexTangents&&e.flatShading===!1?"#define USE_TANGENT":"",e.vertexColors||e.instancingColor||e.batchingColor?"#define USE_COLOR":"",e.vertexAlphas?"#define USE_COLOR_ALPHA":"",e.vertexUv1s?"#define USE_UV1":"",e.vertexUv2s?"#define USE_UV2":"",e.vertexUv3s?"#define USE_UV3":"",e.pointsUvs?"#define USE_POINTS_UV":"",e.gradientMap?"#define USE_GRADIENTMAP":"",e.flatShading?"#define FLAT_SHADED":"",e.doubleSided?"#define DOUBLE_SIDED":"",e.flipSided?"#define FLIP_SIDED":"",e.shadowMapEnabled?"#define USE_SHADOWMAP":"",e.shadowMapEnabled?"#define "+l:"",e.premultipliedAlpha?"#define PREMULTIPLIED_ALPHA":"",e.numLightProbes>0?"#define USE_LIGHT_PROBES":"",e.decodeVideoTexture?"#define DECODE_VIDEO_TEXTURE":"",e.logarithmicDepthBuffer?"#define USE_LOGDEPTHBUF":"",e.reverseDepthBuffer?"#define USE_REVERSEDEPTHBUF":"","uniform mat4 viewMatrix;","uniform vec3 cameraPosition;","uniform bool isOrthographic;",e.toneMapping!==Dn?"#define TONE_MAPPING":"",e.toneMapping!==Dn?Ft.tonemapping_pars_fragment:"",e.toneMapping!==Dn?jp("toneMapping",e.toneMapping):"",e.dithering?"#define DITHERING":"",e.opaque?"#define OPAQUE":"",Ft.colorspace_pars_fragment,Kp("linearToOutputTexel",e.outputColorSpace),Zp(),e.useDepthPacking?"#define DEPTH_PACKING "+e.depthPacking:"",`
`].filter($i).join(`
`)),a=La(a),a=qo(a,e),a=Ko(a,e),o=La(o),o=qo(o,e),o=Ko(o,e),a=jo(a),o=jo(o),e.isRawShaderMaterial!==!0&&(y=`#version 300 es
`,m=[f,"#define attribute in","#define varying out","#define texture2D texture"].join(`
`)+`
`+m,p=["#define varying in",e.glslVersion===uo?"":"layout(location = 0) out highp vec4 pc_fragColor;",e.glslVersion===uo?"":"#define gl_FragColor pc_fragColor","#define gl_FragDepthEXT gl_FragDepth","#define texture2D texture","#define textureCube texture","#define texture2DProj textureProj","#define texture2DLodEXT textureLod","#define texture2DProjLodEXT textureProjLod","#define textureCubeLodEXT textureLod","#define texture2DGradEXT textureGrad","#define texture2DProjGradEXT textureProjGrad","#define textureCubeGradEXT textureGrad"].join(`
`)+`
`+p);const _=y+m+a,S=y+p+o,P=Xo(s,s.VERTEX_SHADER,_),T=Xo(s,s.FRAGMENT_SHADER,S);s.attachShader(v,P),s.attachShader(v,T),e.index0AttributeName!==void 0?s.bindAttribLocation(v,0,e.index0AttributeName):e.morphTargets===!0&&s.bindAttribLocation(v,0,"position"),s.linkProgram(v);function A(E){if(i.debug.checkShaderErrors){const z=s.getProgramInfoLog(v).trim(),V=s.getShaderInfoLog(P).trim(),K=s.getShaderInfoLog(T).trim();let G=!0,I=!0;if(s.getProgramParameter(v,s.LINK_STATUS)===!1)if(G=!1,typeof i.debug.onShaderError=="function")i.debug.onShaderError(s,v,P,T);else{const F=Yo(s,P,"vertex"),O=Yo(s,T,"fragment");console.error("THREE.WebGLProgram: Shader Error "+s.getError()+" - VALIDATE_STATUS "+s.getProgramParameter(v,s.VALIDATE_STATUS)+`

Material Name: `+E.name+`
Material Type: `+E.type+`

Program Info Log: `+z+`
`+F+`
`+O)}else z!==""?console.warn("THREE.WebGLProgram: Program Info Log:",z):(V===""||K==="")&&(I=!1);I&&(E.diagnostics={runnable:G,programLog:z,vertexShader:{log:V,prefix:m},fragmentShader:{log:K,prefix:p}})}s.deleteShader(P),s.deleteShader(T),L=new Ys(s,v),q=Qp(s,v)}let L;this.getUniforms=function(){return L===void 0&&A(this),L};let q;this.getAttributes=function(){return q===void 0&&A(this),q};let x=e.rendererExtensionParallelShaderCompile===!1;return this.isReady=function(){return x===!1&&(x=s.getProgramParameter(v,Wp)),x},this.destroy=function(){n.releaseStatesOfProgram(this),s.deleteProgram(v),this.program=void 0},this.type=e.shaderType,this.name=e.shaderName,this.id=Xp++,this.cacheKey=t,this.usedTimes=1,this.program=v,this.vertexShader=P,this.fragmentShader=T,this}let um=0;class dm{constructor(){this.shaderCache=new Map,this.materialCache=new Map}update(t){const e=t.vertexShader,n=t.fragmentShader,s=this._getShaderStage(e),r=this._getShaderStage(n),a=this._getShaderCacheForMaterial(t);return a.has(s)===!1&&(a.add(s),s.usedTimes++),a.has(r)===!1&&(a.add(r),r.usedTimes++),this}remove(t){const e=this.materialCache.get(t);for(const n of e)n.usedTimes--,n.usedTimes===0&&this.shaderCache.delete(n.code);return this.materialCache.delete(t),this}getVertexShaderID(t){return this._getShaderStage(t.vertexShader).id}getFragmentShaderID(t){return this._getShaderStage(t.fragmentShader).id}dispose(){this.shaderCache.clear(),this.materialCache.clear()}_getShaderCacheForMaterial(t){const e=this.materialCache;let n=e.get(t);return n===void 0&&(n=new Set,e.set(t,n)),n}_getShaderStage(t){const e=this.shaderCache;let n=e.get(t);return n===void 0&&(n=new fm(t),e.set(t,n)),n}}class fm{constructor(t){this.id=um++,this.code=t,this.usedTimes=0}}function pm(i,t,e,n,s,r,a){const o=new Ya,l=new dm,h=new Set,d=[],c=s.logarithmicDepthBuffer,u=s.reverseDepthBuffer,f=s.vertexTextures;let g=s.precision;const v={MeshDepthMaterial:"depth",MeshDistanceMaterial:"distanceRGBA",MeshNormalMaterial:"normal",MeshBasicMaterial:"basic",MeshLambertMaterial:"lambert",MeshPhongMaterial:"phong",MeshToonMaterial:"toon",MeshStandardMaterial:"physical",MeshPhysicalMaterial:"physical",MeshMatcapMaterial:"matcap",LineBasicMaterial:"basic",LineDashedMaterial:"dashed",PointsMaterial:"points",ShadowMaterial:"shadow",SpriteMaterial:"sprite"};function m(x){return h.add(x),x===0?"uv":`uv${x}`}function p(x,E,z,V,K){const G=V.fog,I=K.geometry,F=x.isMeshStandardMaterial?V.environment:null,O=(x.isMeshStandardMaterial?e:t).get(x.envMap||F),Q=O&&O.mapping===nr?O.image.height:null,nt=v[x.type];x.precision!==null&&(g=s.getMaxPrecision(x.precision),g!==x.precision&&console.warn("THREE.WebGLProgram.getParameters:",x.precision,"not supported, using",g,"instead."));const rt=I.morphAttributes.position||I.morphAttributes.normal||I.morphAttributes.color,ht=rt!==void 0?rt.length:0;let ot=0;I.morphAttributes.position!==void 0&&(ot=1),I.morphAttributes.normal!==void 0&&(ot=2),I.morphAttributes.color!==void 0&&(ot=3);let W,J,it,pt;if(nt){const Ie=ln[nt];W=Ie.vertexShader,J=Ie.fragmentShader}else W=x.vertexShader,J=x.fragmentShader,l.update(x),it=l.getVertexShaderID(x),pt=l.getFragmentShaderID(x);const mt=i.getRenderTarget(),Tt=K.isInstancedMesh===!0,kt=K.isBatchedMesh===!0,Kt=!!x.map,Bt=!!x.matcap,C=!!O,ye=!!x.aoMap,Ut=!!x.lightMap,Gt=!!x.bumpMap,ut=!!x.normalMap,At=!!x.displacementMap,bt=!!x.emissiveMap,b=!!x.metalnessMap,M=!!x.roughnessMap,B=x.anisotropy>0,Y=x.clearcoat>0,Z=x.dispersion>0,j=x.iridescence>0,St=x.sheen>0,at=x.transmission>0,gt=B&&!!x.anisotropyMap,qt=Y&&!!x.clearcoatMap,tt=Y&&!!x.clearcoatNormalMap,_t=Y&&!!x.clearcoatRoughnessMap,Dt=j&&!!x.iridescenceMap,It=j&&!!x.iridescenceThicknessMap,xt=St&&!!x.sheenColorMap,Vt=St&&!!x.sheenRoughnessMap,Nt=!!x.specularMap,ne=!!x.specularColorMap,D=!!x.specularIntensityMap,dt=at&&!!x.transmissionMap,X=at&&!!x.thicknessMap,$=!!x.gradientMap,lt=!!x.alphaMap,ft=x.alphaTest>0,Xt=!!x.alphaHash,he=!!x.extensions;let De=Dn;x.toneMapped&&(mt===null||mt.isXRRenderTarget===!0)&&(De=i.toneMapping);const jt={shaderID:nt,shaderType:x.type,shaderName:x.name,vertexShader:W,fragmentShader:J,defines:x.defines,customVertexShaderID:it,customFragmentShaderID:pt,isRawShaderMaterial:x.isRawShaderMaterial===!0,glslVersion:x.glslVersion,precision:g,batching:kt,batchingColor:kt&&K._colorsTexture!==null,instancing:Tt,instancingColor:Tt&&K.instanceColor!==null,instancingMorph:Tt&&K.morphTexture!==null,supportsVertexTextures:f,outputColorSpace:mt===null?i.outputColorSpace:mt.isXRRenderTarget===!0?mt.texture.colorSpace:In,alphaToCoverage:!!x.alphaToCoverage,map:Kt,matcap:Bt,envMap:C,envMapMode:C&&O.mapping,envMapCubeUVHeight:Q,aoMap:ye,lightMap:Ut,bumpMap:Gt,normalMap:ut,displacementMap:f&&At,emissiveMap:bt,normalMapObjectSpace:ut&&x.normalMapType===ih,normalMapTangentSpace:ut&&x.normalMapType===Vl,metalnessMap:b,roughnessMap:M,anisotropy:B,anisotropyMap:gt,clearcoat:Y,clearcoatMap:qt,clearcoatNormalMap:tt,clearcoatRoughnessMap:_t,dispersion:Z,iridescence:j,iridescenceMap:Dt,iridescenceThicknessMap:It,sheen:St,sheenColorMap:xt,sheenRoughnessMap:Vt,specularMap:Nt,specularColorMap:ne,specularIntensityMap:D,transmission:at,transmissionMap:dt,thicknessMap:X,gradientMap:$,opaque:x.transparent===!1&&x.blending===Ei&&x.alphaToCoverage===!1,alphaMap:lt,alphaTest:ft,alphaHash:Xt,combine:x.combine,mapUv:Kt&&m(x.map.channel),aoMapUv:ye&&m(x.aoMap.channel),lightMapUv:Ut&&m(x.lightMap.channel),bumpMapUv:Gt&&m(x.bumpMap.channel),normalMapUv:ut&&m(x.normalMap.channel),displacementMapUv:At&&m(x.displacementMap.channel),emissiveMapUv:bt&&m(x.emissiveMap.channel),metalnessMapUv:b&&m(x.metalnessMap.channel),roughnessMapUv:M&&m(x.roughnessMap.channel),anisotropyMapUv:gt&&m(x.anisotropyMap.channel),clearcoatMapUv:qt&&m(x.clearcoatMap.channel),clearcoatNormalMapUv:tt&&m(x.clearcoatNormalMap.channel),clearcoatRoughnessMapUv:_t&&m(x.clearcoatRoughnessMap.channel),iridescenceMapUv:Dt&&m(x.iridescenceMap.channel),iridescenceThicknessMapUv:It&&m(x.iridescenceThicknessMap.channel),sheenColorMapUv:xt&&m(x.sheenColorMap.channel),sheenRoughnessMapUv:Vt&&m(x.sheenRoughnessMap.channel),specularMapUv:Nt&&m(x.specularMap.channel),specularColorMapUv:ne&&m(x.specularColorMap.channel),specularIntensityMapUv:D&&m(x.specularIntensityMap.channel),transmissionMapUv:dt&&m(x.transmissionMap.channel),thicknessMapUv:X&&m(x.thicknessMap.channel),alphaMapUv:lt&&m(x.alphaMap.channel),vertexTangents:!!I.attributes.tangent&&(ut||B),vertexColors:x.vertexColors,vertexAlphas:x.vertexColors===!0&&!!I.attributes.color&&I.attributes.color.itemSize===4,pointsUvs:K.isPoints===!0&&!!I.attributes.uv&&(Kt||lt),fog:!!G,useFog:x.fog===!0,fogExp2:!!G&&G.isFogExp2,flatShading:x.flatShading===!0,sizeAttenuation:x.sizeAttenuation===!0,logarithmicDepthBuffer:c,reverseDepthBuffer:u,skinning:K.isSkinnedMesh===!0,morphTargets:I.morphAttributes.position!==void 0,morphNormals:I.morphAttributes.normal!==void 0,morphColors:I.morphAttributes.color!==void 0,morphTargetsCount:ht,morphTextureStride:ot,numDirLights:E.directional.length,numPointLights:E.point.length,numSpotLights:E.spot.length,numSpotLightMaps:E.spotLightMap.length,numRectAreaLights:E.rectArea.length,numHemiLights:E.hemi.length,numDirLightShadows:E.directionalShadowMap.length,numPointLightShadows:E.pointShadowMap.length,numSpotLightShadows:E.spotShadowMap.length,numSpotLightShadowsWithMaps:E.numSpotLightShadowsWithMaps,numLightProbes:E.numLightProbes,numClippingPlanes:a.numPlanes,numClipIntersection:a.numIntersection,dithering:x.dithering,shadowMapEnabled:i.shadowMap.enabled&&z.length>0,shadowMapType:i.shadowMap.type,toneMapping:De,decodeVideoTexture:Kt&&x.map.isVideoTexture===!0&&Jt.getTransfer(x.map.colorSpace)===se,premultipliedAlpha:x.premultipliedAlpha,doubleSided:x.side===de,flipSided:x.side===Pe,useDepthPacking:x.depthPacking>=0,depthPacking:x.depthPacking||0,index0AttributeName:x.index0AttributeName,extensionClipCullDistance:he&&x.extensions.clipCullDistance===!0&&n.has("WEBGL_clip_cull_distance"),extensionMultiDraw:(he&&x.extensions.multiDraw===!0||kt)&&n.has("WEBGL_multi_draw"),rendererExtensionParallelShaderCompile:n.has("KHR_parallel_shader_compile"),customProgramCacheKey:x.customProgramCacheKey()};return jt.vertexUv1s=h.has(1),jt.vertexUv2s=h.has(2),jt.vertexUv3s=h.has(3),h.clear(),jt}function y(x){const E=[];if(x.shaderID?E.push(x.shaderID):(E.push(x.customVertexShaderID),E.push(x.customFragmentShaderID)),x.defines!==void 0)for(const z in x.defines)E.push(z),E.push(x.defines[z]);return x.isRawShaderMaterial===!1&&(_(E,x),S(E,x),E.push(i.outputColorSpace)),E.push(x.customProgramCacheKey),E.join()}function _(x,E){x.push(E.precision),x.push(E.outputColorSpace),x.push(E.envMapMode),x.push(E.envMapCubeUVHeight),x.push(E.mapUv),x.push(E.alphaMapUv),x.push(E.lightMapUv),x.push(E.aoMapUv),x.push(E.bumpMapUv),x.push(E.normalMapUv),x.push(E.displacementMapUv),x.push(E.emissiveMapUv),x.push(E.metalnessMapUv),x.push(E.roughnessMapUv),x.push(E.anisotropyMapUv),x.push(E.clearcoatMapUv),x.push(E.clearcoatNormalMapUv),x.push(E.clearcoatRoughnessMapUv),x.push(E.iridescenceMapUv),x.push(E.iridescenceThicknessMapUv),x.push(E.sheenColorMapUv),x.push(E.sheenRoughnessMapUv),x.push(E.specularMapUv),x.push(E.specularColorMapUv),x.push(E.specularIntensityMapUv),x.push(E.transmissionMapUv),x.push(E.thicknessMapUv),x.push(E.combine),x.push(E.fogExp2),x.push(E.sizeAttenuation),x.push(E.morphTargetsCount),x.push(E.morphAttributeCount),x.push(E.numDirLights),x.push(E.numPointLights),x.push(E.numSpotLights),x.push(E.numSpotLightMaps),x.push(E.numHemiLights),x.push(E.numRectAreaLights),x.push(E.numDirLightShadows),x.push(E.numPointLightShadows),x.push(E.numSpotLightShadows),x.push(E.numSpotLightShadowsWithMaps),x.push(E.numLightProbes),x.push(E.shadowMapType),x.push(E.toneMapping),x.push(E.numClippingPlanes),x.push(E.numClipIntersection),x.push(E.depthPacking)}function S(x,E){o.disableAll(),E.supportsVertexTextures&&o.enable(0),E.instancing&&o.enable(1),E.instancingColor&&o.enable(2),E.instancingMorph&&o.enable(3),E.matcap&&o.enable(4),E.envMap&&o.enable(5),E.normalMapObjectSpace&&o.enable(6),E.normalMapTangentSpace&&o.enable(7),E.clearcoat&&o.enable(8),E.iridescence&&o.enable(9),E.alphaTest&&o.enable(10),E.vertexColors&&o.enable(11),E.vertexAlphas&&o.enable(12),E.vertexUv1s&&o.enable(13),E.vertexUv2s&&o.enable(14),E.vertexUv3s&&o.enable(15),E.vertexTangents&&o.enable(16),E.anisotropy&&o.enable(17),E.alphaHash&&o.enable(18),E.batching&&o.enable(19),E.dispersion&&o.enable(20),E.batchingColor&&o.enable(21),x.push(o.mask),o.disableAll(),E.fog&&o.enable(0),E.useFog&&o.enable(1),E.flatShading&&o.enable(2),E.logarithmicDepthBuffer&&o.enable(3),E.reverseDepthBuffer&&o.enable(4),E.skinning&&o.enable(5),E.morphTargets&&o.enable(6),E.morphNormals&&o.enable(7),E.morphColors&&o.enable(8),E.premultipliedAlpha&&o.enable(9),E.shadowMapEnabled&&o.enable(10),E.doubleSided&&o.enable(11),E.flipSided&&o.enable(12),E.useDepthPacking&&o.enable(13),E.dithering&&o.enable(14),E.transmission&&o.enable(15),E.sheen&&o.enable(16),E.opaque&&o.enable(17),E.pointsUvs&&o.enable(18),E.decodeVideoTexture&&o.enable(19),E.alphaToCoverage&&o.enable(20),x.push(o.mask)}function P(x){const E=v[x.type];let z;if(E){const V=ln[E];z=Zh.clone(V.uniforms)}else z=x.uniforms;return z}function T(x,E){let z;for(let V=0,K=d.length;V<K;V++){const G=d[V];if(G.cacheKey===E){z=G,++z.usedTimes;break}}return z===void 0&&(z=new hm(i,E,x,r),d.push(z)),z}function A(x){if(--x.usedTimes===0){const E=d.indexOf(x);d[E]=d[d.length-1],d.pop(),x.destroy()}}function L(x){l.remove(x)}function q(){l.dispose()}return{getParameters:p,getProgramCacheKey:y,getUniforms:P,acquireProgram:T,releaseProgram:A,releaseShaderCache:L,programs:d,dispose:q}}function mm(){let i=new WeakMap;function t(a){return i.has(a)}function e(a){let o=i.get(a);return o===void 0&&(o={},i.set(a,o)),o}function n(a){i.delete(a)}function s(a,o,l){i.get(a)[o]=l}function r(){i=new WeakMap}return{has:t,get:e,remove:n,update:s,dispose:r}}function gm(i,t){return i.groupOrder!==t.groupOrder?i.groupOrder-t.groupOrder:i.renderOrder!==t.renderOrder?i.renderOrder-t.renderOrder:i.material.id!==t.material.id?i.material.id-t.material.id:i.z!==t.z?i.z-t.z:i.id-t.id}function $o(i,t){return i.groupOrder!==t.groupOrder?i.groupOrder-t.groupOrder:i.renderOrder!==t.renderOrder?i.renderOrder-t.renderOrder:i.z!==t.z?t.z-i.z:i.id-t.id}function Jo(){const i=[];let t=0;const e=[],n=[],s=[];function r(){t=0,e.length=0,n.length=0,s.length=0}function a(c,u,f,g,v,m){let p=i[t];return p===void 0?(p={id:c.id,object:c,geometry:u,material:f,groupOrder:g,renderOrder:c.renderOrder,z:v,group:m},i[t]=p):(p.id=c.id,p.object=c,p.geometry=u,p.material=f,p.groupOrder=g,p.renderOrder=c.renderOrder,p.z=v,p.group=m),t++,p}function o(c,u,f,g,v,m){const p=a(c,u,f,g,v,m);f.transmission>0?n.push(p):f.transparent===!0?s.push(p):e.push(p)}function l(c,u,f,g,v,m){const p=a(c,u,f,g,v,m);f.transmission>0?n.unshift(p):f.transparent===!0?s.unshift(p):e.unshift(p)}function h(c,u){e.length>1&&e.sort(c||gm),n.length>1&&n.sort(u||$o),s.length>1&&s.sort(u||$o)}function d(){for(let c=t,u=i.length;c<u;c++){const f=i[c];if(f.id===null)break;f.id=null,f.object=null,f.geometry=null,f.material=null,f.group=null}}return{opaque:e,transmissive:n,transparent:s,init:r,push:o,unshift:l,finish:d,sort:h}}function _m(){let i=new WeakMap;function t(n,s){const r=i.get(n);let a;return r===void 0?(a=new Jo,i.set(n,[a])):s>=r.length?(a=new Jo,r.push(a)):a=r[s],a}function e(){i=new WeakMap}return{get:t,dispose:e}}function xm(){const i={};return{get:function(t){if(i[t.id]!==void 0)return i[t.id];let e;switch(t.type){case"DirectionalLight":e={direction:new R,color:new Pt};break;case"SpotLight":e={position:new R,direction:new R,color:new Pt,distance:0,coneCos:0,penumbraCos:0,decay:0};break;case"PointLight":e={position:new R,color:new Pt,distance:0,decay:0};break;case"HemisphereLight":e={direction:new R,skyColor:new Pt,groundColor:new Pt};break;case"RectAreaLight":e={color:new Pt,position:new R,halfWidth:new R,halfHeight:new R};break}return i[t.id]=e,e}}}function vm(){const i={};return{get:function(t){if(i[t.id]!==void 0)return i[t.id];let e;switch(t.type){case"DirectionalLight":e={shadowIntensity:1,shadowBias:0,shadowNormalBias:0,shadowRadius:1,shadowMapSize:new Ht};break;case"SpotLight":e={shadowIntensity:1,shadowBias:0,shadowNormalBias:0,shadowRadius:1,shadowMapSize:new Ht};break;case"PointLight":e={shadowIntensity:1,shadowBias:0,shadowNormalBias:0,shadowRadius:1,shadowMapSize:new Ht,shadowCameraNear:1,shadowCameraFar:1e3};break}return i[t.id]=e,e}}}let Mm=0;function ym(i,t){return(t.castShadow?2:0)-(i.castShadow?2:0)+(t.map?1:0)-(i.map?1:0)}function Sm(i){const t=new xm,e=vm(),n={version:0,hash:{directionalLength:-1,pointLength:-1,spotLength:-1,rectAreaLength:-1,hemiLength:-1,numDirectionalShadows:-1,numPointShadows:-1,numSpotShadows:-1,numSpotMaps:-1,numLightProbes:-1},ambient:[0,0,0],probe:[],directional:[],directionalShadow:[],directionalShadowMap:[],directionalShadowMatrix:[],spot:[],spotLightMap:[],spotShadow:[],spotShadowMap:[],spotLightMatrix:[],rectArea:[],rectAreaLTC1:null,rectAreaLTC2:null,point:[],pointShadow:[],pointShadowMap:[],pointShadowMatrix:[],hemi:[],numSpotLightShadowsWithMaps:0,numLightProbes:0};for(let h=0;h<9;h++)n.probe.push(new R);const s=new R,r=new ee,a=new ee;function o(h){let d=0,c=0,u=0;for(let q=0;q<9;q++)n.probe[q].set(0,0,0);let f=0,g=0,v=0,m=0,p=0,y=0,_=0,S=0,P=0,T=0,A=0;h.sort(ym);for(let q=0,x=h.length;q<x;q++){const E=h[q],z=E.color,V=E.intensity,K=E.distance,G=E.shadow&&E.shadow.map?E.shadow.map.texture:null;if(E.isAmbientLight)d+=z.r*V,c+=z.g*V,u+=z.b*V;else if(E.isLightProbe){for(let I=0;I<9;I++)n.probe[I].addScaledVector(E.sh.coefficients[I],V);A++}else if(E.isDirectionalLight){const I=t.get(E);if(I.color.copy(E.color).multiplyScalar(E.intensity),E.castShadow){const F=E.shadow,O=e.get(E);O.shadowIntensity=F.intensity,O.shadowBias=F.bias,O.shadowNormalBias=F.normalBias,O.shadowRadius=F.radius,O.shadowMapSize=F.mapSize,n.directionalShadow[f]=O,n.directionalShadowMap[f]=G,n.directionalShadowMatrix[f]=E.shadow.matrix,y++}n.directional[f]=I,f++}else if(E.isSpotLight){const I=t.get(E);I.position.setFromMatrixPosition(E.matrixWorld),I.color.copy(z).multiplyScalar(V),I.distance=K,I.coneCos=Math.cos(E.angle),I.penumbraCos=Math.cos(E.angle*(1-E.penumbra)),I.decay=E.decay,n.spot[v]=I;const F=E.shadow;if(E.map&&(n.spotLightMap[P]=E.map,P++,F.updateMatrices(E),E.castShadow&&T++),n.spotLightMatrix[v]=F.matrix,E.castShadow){const O=e.get(E);O.shadowIntensity=F.intensity,O.shadowBias=F.bias,O.shadowNormalBias=F.normalBias,O.shadowRadius=F.radius,O.shadowMapSize=F.mapSize,n.spotShadow[v]=O,n.spotShadowMap[v]=G,S++}v++}else if(E.isRectAreaLight){const I=t.get(E);I.color.copy(z).multiplyScalar(V),I.halfWidth.set(E.width*.5,0,0),I.halfHeight.set(0,E.height*.5,0),n.rectArea[m]=I,m++}else if(E.isPointLight){const I=t.get(E);if(I.color.copy(E.color).multiplyScalar(E.intensity),I.distance=E.distance,I.decay=E.decay,E.castShadow){const F=E.shadow,O=e.get(E);O.shadowIntensity=F.intensity,O.shadowBias=F.bias,O.shadowNormalBias=F.normalBias,O.shadowRadius=F.radius,O.shadowMapSize=F.mapSize,O.shadowCameraNear=F.camera.near,O.shadowCameraFar=F.camera.far,n.pointShadow[g]=O,n.pointShadowMap[g]=G,n.pointShadowMatrix[g]=E.shadow.matrix,_++}n.point[g]=I,g++}else if(E.isHemisphereLight){const I=t.get(E);I.skyColor.copy(E.color).multiplyScalar(V),I.groundColor.copy(E.groundColor).multiplyScalar(V),n.hemi[p]=I,p++}}m>0&&(i.has("OES_texture_float_linear")===!0?(n.rectAreaLTC1=st.LTC_FLOAT_1,n.rectAreaLTC2=st.LTC_FLOAT_2):(n.rectAreaLTC1=st.LTC_HALF_1,n.rectAreaLTC2=st.LTC_HALF_2)),n.ambient[0]=d,n.ambient[1]=c,n.ambient[2]=u;const L=n.hash;(L.directionalLength!==f||L.pointLength!==g||L.spotLength!==v||L.rectAreaLength!==m||L.hemiLength!==p||L.numDirectionalShadows!==y||L.numPointShadows!==_||L.numSpotShadows!==S||L.numSpotMaps!==P||L.numLightProbes!==A)&&(n.directional.length=f,n.spot.length=v,n.rectArea.length=m,n.point.length=g,n.hemi.length=p,n.directionalShadow.length=y,n.directionalShadowMap.length=y,n.pointShadow.length=_,n.pointShadowMap.length=_,n.spotShadow.length=S,n.spotShadowMap.length=S,n.directionalShadowMatrix.length=y,n.pointShadowMatrix.length=_,n.spotLightMatrix.length=S+P-T,n.spotLightMap.length=P,n.numSpotLightShadowsWithMaps=T,n.numLightProbes=A,L.directionalLength=f,L.pointLength=g,L.spotLength=v,L.rectAreaLength=m,L.hemiLength=p,L.numDirectionalShadows=y,L.numPointShadows=_,L.numSpotShadows=S,L.numSpotMaps=P,L.numLightProbes=A,n.version=Mm++)}function l(h,d){let c=0,u=0,f=0,g=0,v=0;const m=d.matrixWorldInverse;for(let p=0,y=h.length;p<y;p++){const _=h[p];if(_.isDirectionalLight){const S=n.directional[c];S.direction.setFromMatrixPosition(_.matrixWorld),s.setFromMatrixPosition(_.target.matrixWorld),S.direction.sub(s),S.direction.transformDirection(m),c++}else if(_.isSpotLight){const S=n.spot[f];S.position.setFromMatrixPosition(_.matrixWorld),S.position.applyMatrix4(m),S.direction.setFromMatrixPosition(_.matrixWorld),s.setFromMatrixPosition(_.target.matrixWorld),S.direction.sub(s),S.direction.transformDirection(m),f++}else if(_.isRectAreaLight){const S=n.rectArea[g];S.position.setFromMatrixPosition(_.matrixWorld),S.position.applyMatrix4(m),a.identity(),r.copy(_.matrixWorld),r.premultiply(m),a.extractRotation(r),S.halfWidth.set(_.width*.5,0,0),S.halfHeight.set(0,_.height*.5,0),S.halfWidth.applyMatrix4(a),S.halfHeight.applyMatrix4(a),g++}else if(_.isPointLight){const S=n.point[u];S.position.setFromMatrixPosition(_.matrixWorld),S.position.applyMatrix4(m),u++}else if(_.isHemisphereLight){const S=n.hemi[v];S.direction.setFromMatrixPosition(_.matrixWorld),S.direction.transformDirection(m),v++}}}return{setup:o,setupView:l,state:n}}function Qo(i){const t=new Sm(i),e=[],n=[];function s(d){h.camera=d,e.length=0,n.length=0}function r(d){e.push(d)}function a(d){n.push(d)}function o(){t.setup(e)}function l(d){t.setupView(e,d)}const h={lightsArray:e,shadowsArray:n,camera:null,lights:t,transmissionRenderTarget:{}};return{init:s,state:h,setupLights:o,setupLightsView:l,pushLight:r,pushShadow:a}}function wm(i){let t=new WeakMap;function e(s,r=0){const a=t.get(s);let o;return a===void 0?(o=new Qo(i),t.set(s,[o])):r>=a.length?(o=new Qo(i),a.push(o)):o=a[r],o}function n(){t=new WeakMap}return{get:e,dispose:n}}class Em extends Bi{constructor(t){super(),this.isMeshDepthMaterial=!0,this.type="MeshDepthMaterial",this.depthPacking=eh,this.map=null,this.alphaMap=null,this.displacementMap=null,this.displacementScale=1,this.displacementBias=0,this.wireframe=!1,this.wireframeLinewidth=1,this.setValues(t)}copy(t){return super.copy(t),this.depthPacking=t.depthPacking,this.map=t.map,this.alphaMap=t.alphaMap,this.displacementMap=t.displacementMap,this.displacementScale=t.displacementScale,this.displacementBias=t.displacementBias,this.wireframe=t.wireframe,this.wireframeLinewidth=t.wireframeLinewidth,this}}class bm extends Bi{constructor(t){super(),this.isMeshDistanceMaterial=!0,this.type="MeshDistanceMaterial",this.map=null,this.alphaMap=null,this.displacementMap=null,this.displacementScale=1,this.displacementBias=0,this.setValues(t)}copy(t){return super.copy(t),this.map=t.map,this.alphaMap=t.alphaMap,this.displacementMap=t.displacementMap,this.displacementScale=t.displacementScale,this.displacementBias=t.displacementBias,this}}const Tm=`void main() {
	gl_Position = vec4( position, 1.0 );
}`,Am=`uniform sampler2D shadow_pass;
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
}`;function Rm(i,t,e){let n=new qa;const s=new Ht,r=new Ht,a=new te,o=new Em({depthPacking:nh}),l=new bm,h={},d=e.maxTextureSize,c={[hn]:Pe,[Pe]:hn,[de]:de},u=new an({defines:{VSM_SAMPLES:8},uniforms:{shadow_pass:{value:null},resolution:{value:new Ht},radius:{value:4}},vertexShader:Tm,fragmentShader:Am}),f=u.clone();f.defines.HORIZONTAL_PASS=1;const g=new Le;g.setAttribute("position",new Xe(new Float32Array([-1,-1,.5,3,-1,.5,-1,3,.5]),3));const v=new Ct(g,u),m=this;this.enabled=!1,this.autoUpdate=!0,this.needsUpdate=!1,this.type=Pl;let p=this.type;this.render=function(T,A,L){if(m.enabled===!1||m.autoUpdate===!1&&m.needsUpdate===!1||T.length===0)return;const q=i.getRenderTarget(),x=i.getActiveCubeFace(),E=i.getActiveMipmapLevel(),z=i.state;z.setBlending(Ln),z.buffers.color.setClear(1,1,1,1),z.buffers.depth.setTest(!0),z.setScissorTest(!1);const V=p!==_n&&this.type===_n,K=p===_n&&this.type!==_n;for(let G=0,I=T.length;G<I;G++){const F=T[G],O=F.shadow;if(O===void 0){console.warn("THREE.WebGLShadowMap:",F,"has no shadow.");continue}if(O.autoUpdate===!1&&O.needsUpdate===!1)continue;s.copy(O.mapSize);const Q=O.getFrameExtents();if(s.multiply(Q),r.copy(O.mapSize),(s.x>d||s.y>d)&&(s.x>d&&(r.x=Math.floor(d/Q.x),s.x=r.x*Q.x,O.mapSize.x=r.x),s.y>d&&(r.y=Math.floor(d/Q.y),s.y=r.y*Q.y,O.mapSize.y=r.y)),O.map===null||V===!0||K===!0){const rt=this.type!==_n?{minFilter:Ue,magFilter:Ue}:{};O.map!==null&&O.map.dispose(),O.map=new $n(s.x,s.y,rt),O.map.texture.name=F.name+".shadowMap",O.camera.updateProjectionMatrix()}i.setRenderTarget(O.map),i.clear();const nt=O.getViewportCount();for(let rt=0;rt<nt;rt++){const ht=O.getViewport(rt);a.set(r.x*ht.x,r.y*ht.y,r.x*ht.z,r.y*ht.w),z.viewport(a),O.updateMatrices(F,rt),n=O.getFrustum(),S(A,L,O.camera,F,this.type)}O.isPointLightShadow!==!0&&this.type===_n&&y(O,L),O.needsUpdate=!1}p=this.type,m.needsUpdate=!1,i.setRenderTarget(q,x,E)};function y(T,A){const L=t.update(v);u.defines.VSM_SAMPLES!==T.blurSamples&&(u.defines.VSM_SAMPLES=T.blurSamples,f.defines.VSM_SAMPLES=T.blurSamples,u.needsUpdate=!0,f.needsUpdate=!0),T.mapPass===null&&(T.mapPass=new $n(s.x,s.y)),u.uniforms.shadow_pass.value=T.map.texture,u.uniforms.resolution.value=T.mapSize,u.uniforms.radius.value=T.radius,i.setRenderTarget(T.mapPass),i.clear(),i.renderBufferDirect(A,null,L,u,v,null),f.uniforms.shadow_pass.value=T.mapPass.texture,f.uniforms.resolution.value=T.mapSize,f.uniforms.radius.value=T.radius,i.setRenderTarget(T.map),i.clear(),i.renderBufferDirect(A,null,L,f,v,null)}function _(T,A,L,q){let x=null;const E=L.isPointLight===!0?T.customDistanceMaterial:T.customDepthMaterial;if(E!==void 0)x=E;else if(x=L.isPointLight===!0?l:o,i.localClippingEnabled&&A.clipShadows===!0&&Array.isArray(A.clippingPlanes)&&A.clippingPlanes.length!==0||A.displacementMap&&A.displacementScale!==0||A.alphaMap&&A.alphaTest>0||A.map&&A.alphaTest>0){const z=x.uuid,V=A.uuid;let K=h[z];K===void 0&&(K={},h[z]=K);let G=K[V];G===void 0&&(G=x.clone(),K[V]=G,A.addEventListener("dispose",P)),x=G}if(x.visible=A.visible,x.wireframe=A.wireframe,q===_n?x.side=A.shadowSide!==null?A.shadowSide:A.side:x.side=A.shadowSide!==null?A.shadowSide:c[A.side],x.alphaMap=A.alphaMap,x.alphaTest=A.alphaTest,x.map=A.map,x.clipShadows=A.clipShadows,x.clippingPlanes=A.clippingPlanes,x.clipIntersection=A.clipIntersection,x.displacementMap=A.displacementMap,x.displacementScale=A.displacementScale,x.displacementBias=A.displacementBias,x.wireframeLinewidth=A.wireframeLinewidth,x.linewidth=A.linewidth,L.isPointLight===!0&&x.isMeshDistanceMaterial===!0){const z=i.properties.get(x);z.light=L}return x}function S(T,A,L,q,x){if(T.visible===!1)return;if(T.layers.test(A.layers)&&(T.isMesh||T.isLine||T.isPoints)&&(T.castShadow||T.receiveShadow&&x===_n)&&(!T.frustumCulled||n.intersectsObject(T))){T.modelViewMatrix.multiplyMatrices(L.matrixWorldInverse,T.matrixWorld);const V=t.update(T),K=T.material;if(Array.isArray(K)){const G=V.groups;for(let I=0,F=G.length;I<F;I++){const O=G[I],Q=K[O.materialIndex];if(Q&&Q.visible){const nt=_(T,Q,q,x);T.onBeforeShadow(i,T,A,L,V,nt,O),i.renderBufferDirect(L,null,V,nt,T,O),T.onAfterShadow(i,T,A,L,V,nt,O)}}}else if(K.visible){const G=_(T,K,q,x);T.onBeforeShadow(i,T,A,L,V,G,null),i.renderBufferDirect(L,null,V,G,T,null),T.onAfterShadow(i,T,A,L,V,G,null)}}const z=T.children;for(let V=0,K=z.length;V<K;V++)S(z[V],A,L,q,x)}function P(T){T.target.removeEventListener("dispose",P);for(const L in h){const q=h[L],x=T.target.uuid;x in q&&(q[x].dispose(),delete q[x])}}}const Cm={[jr]:Zr,[$r]:ta,[Jr]:ea,[Ri]:Qr,[Zr]:jr,[ta]:$r,[ea]:Jr,[Qr]:Ri};function Pm(i){function t(){let D=!1;const dt=new te;let X=null;const $=new te(0,0,0,0);return{setMask:function(lt){X!==lt&&!D&&(i.colorMask(lt,lt,lt,lt),X=lt)},setLocked:function(lt){D=lt},setClear:function(lt,ft,Xt,he,De){De===!0&&(lt*=he,ft*=he,Xt*=he),dt.set(lt,ft,Xt,he),$.equals(dt)===!1&&(i.clearColor(lt,ft,Xt,he),$.copy(dt))},reset:function(){D=!1,X=null,$.set(-1,0,0,0)}}}function e(){let D=!1,dt=!1,X=null,$=null,lt=null;return{setReversed:function(ft){dt=ft},setTest:function(ft){ft?it(i.DEPTH_TEST):pt(i.DEPTH_TEST)},setMask:function(ft){X!==ft&&!D&&(i.depthMask(ft),X=ft)},setFunc:function(ft){if(dt&&(ft=Cm[ft]),$!==ft){switch(ft){case jr:i.depthFunc(i.NEVER);break;case Zr:i.depthFunc(i.ALWAYS);break;case $r:i.depthFunc(i.LESS);break;case Ri:i.depthFunc(i.LEQUAL);break;case Jr:i.depthFunc(i.EQUAL);break;case Qr:i.depthFunc(i.GEQUAL);break;case ta:i.depthFunc(i.GREATER);break;case ea:i.depthFunc(i.NOTEQUAL);break;default:i.depthFunc(i.LEQUAL)}$=ft}},setLocked:function(ft){D=ft},setClear:function(ft){lt!==ft&&(i.clearDepth(ft),lt=ft)},reset:function(){D=!1,X=null,$=null,lt=null}}}function n(){let D=!1,dt=null,X=null,$=null,lt=null,ft=null,Xt=null,he=null,De=null;return{setTest:function(jt){D||(jt?it(i.STENCIL_TEST):pt(i.STENCIL_TEST))},setMask:function(jt){dt!==jt&&!D&&(i.stencilMask(jt),dt=jt)},setFunc:function(jt,Ie,un){(X!==jt||$!==Ie||lt!==un)&&(i.stencilFunc(jt,Ie,un),X=jt,$=Ie,lt=un)},setOp:function(jt,Ie,un){(ft!==jt||Xt!==Ie||he!==un)&&(i.stencilOp(jt,Ie,un),ft=jt,Xt=Ie,he=un)},setLocked:function(jt){D=jt},setClear:function(jt){De!==jt&&(i.clearStencil(jt),De=jt)},reset:function(){D=!1,dt=null,X=null,$=null,lt=null,ft=null,Xt=null,he=null,De=null}}}const s=new t,r=new e,a=new n,o=new WeakMap,l=new WeakMap;let h={},d={},c=new WeakMap,u=[],f=null,g=!1,v=null,m=null,p=null,y=null,_=null,S=null,P=null,T=new Pt(0,0,0),A=0,L=!1,q=null,x=null,E=null,z=null,V=null;const K=i.getParameter(i.MAX_COMBINED_TEXTURE_IMAGE_UNITS);let G=!1,I=0;const F=i.getParameter(i.VERSION);F.indexOf("WebGL")!==-1?(I=parseFloat(/^WebGL (\d)/.exec(F)[1]),G=I>=1):F.indexOf("OpenGL ES")!==-1&&(I=parseFloat(/^OpenGL ES (\d)/.exec(F)[1]),G=I>=2);let O=null,Q={};const nt=i.getParameter(i.SCISSOR_BOX),rt=i.getParameter(i.VIEWPORT),ht=new te().fromArray(nt),ot=new te().fromArray(rt);function W(D,dt,X,$){const lt=new Uint8Array(4),ft=i.createTexture();i.bindTexture(D,ft),i.texParameteri(D,i.TEXTURE_MIN_FILTER,i.NEAREST),i.texParameteri(D,i.TEXTURE_MAG_FILTER,i.NEAREST);for(let Xt=0;Xt<X;Xt++)D===i.TEXTURE_3D||D===i.TEXTURE_2D_ARRAY?i.texImage3D(dt,0,i.RGBA,1,1,$,0,i.RGBA,i.UNSIGNED_BYTE,lt):i.texImage2D(dt+Xt,0,i.RGBA,1,1,0,i.RGBA,i.UNSIGNED_BYTE,lt);return ft}const J={};J[i.TEXTURE_2D]=W(i.TEXTURE_2D,i.TEXTURE_2D,1),J[i.TEXTURE_CUBE_MAP]=W(i.TEXTURE_CUBE_MAP,i.TEXTURE_CUBE_MAP_POSITIVE_X,6),J[i.TEXTURE_2D_ARRAY]=W(i.TEXTURE_2D_ARRAY,i.TEXTURE_2D_ARRAY,1,1),J[i.TEXTURE_3D]=W(i.TEXTURE_3D,i.TEXTURE_3D,1,1),s.setClear(0,0,0,1),r.setClear(1),a.setClear(0),it(i.DEPTH_TEST),r.setFunc(Ri),Ut(!1),Gt(ao),it(i.CULL_FACE),C(Ln);function it(D){h[D]!==!0&&(i.enable(D),h[D]=!0)}function pt(D){h[D]!==!1&&(i.disable(D),h[D]=!1)}function mt(D,dt){return d[D]!==dt?(i.bindFramebuffer(D,dt),d[D]=dt,D===i.DRAW_FRAMEBUFFER&&(d[i.FRAMEBUFFER]=dt),D===i.FRAMEBUFFER&&(d[i.DRAW_FRAMEBUFFER]=dt),!0):!1}function Tt(D,dt){let X=u,$=!1;if(D){X=c.get(dt),X===void 0&&(X=[],c.set(dt,X));const lt=D.textures;if(X.length!==lt.length||X[0]!==i.COLOR_ATTACHMENT0){for(let ft=0,Xt=lt.length;ft<Xt;ft++)X[ft]=i.COLOR_ATTACHMENT0+ft;X.length=lt.length,$=!0}}else X[0]!==i.BACK&&(X[0]=i.BACK,$=!0);$&&i.drawBuffers(X)}function kt(D){return f!==D?(i.useProgram(D),f=D,!0):!1}const Kt={[qn]:i.FUNC_ADD,[Cc]:i.FUNC_SUBTRACT,[Pc]:i.FUNC_REVERSE_SUBTRACT};Kt[Lc]=i.MIN,Kt[Dc]=i.MAX;const Bt={[Ic]:i.ZERO,[Uc]:i.ONE,[Nc]:i.SRC_COLOR,[qr]:i.SRC_ALPHA,[Hc]:i.SRC_ALPHA_SATURATE,[kc]:i.DST_COLOR,[Oc]:i.DST_ALPHA,[Fc]:i.ONE_MINUS_SRC_COLOR,[Kr]:i.ONE_MINUS_SRC_ALPHA,[zc]:i.ONE_MINUS_DST_COLOR,[Bc]:i.ONE_MINUS_DST_ALPHA,[Gc]:i.CONSTANT_COLOR,[Vc]:i.ONE_MINUS_CONSTANT_COLOR,[Wc]:i.CONSTANT_ALPHA,[Xc]:i.ONE_MINUS_CONSTANT_ALPHA};function C(D,dt,X,$,lt,ft,Xt,he,De,jt){if(D===Ln){g===!0&&(pt(i.BLEND),g=!1);return}if(g===!1&&(it(i.BLEND),g=!0),D!==Rc){if(D!==v||jt!==L){if((m!==qn||_!==qn)&&(i.blendEquation(i.FUNC_ADD),m=qn,_=qn),jt)switch(D){case Ei:i.blendFuncSeparate(i.ONE,i.ONE_MINUS_SRC_ALPHA,i.ONE,i.ONE_MINUS_SRC_ALPHA);break;case Ai:i.blendFunc(i.ONE,i.ONE);break;case oo:i.blendFuncSeparate(i.ZERO,i.ONE_MINUS_SRC_COLOR,i.ZERO,i.ONE);break;case lo:i.blendFuncSeparate(i.ZERO,i.SRC_COLOR,i.ZERO,i.SRC_ALPHA);break;default:console.error("THREE.WebGLState: Invalid blending: ",D);break}else switch(D){case Ei:i.blendFuncSeparate(i.SRC_ALPHA,i.ONE_MINUS_SRC_ALPHA,i.ONE,i.ONE_MINUS_SRC_ALPHA);break;case Ai:i.blendFunc(i.SRC_ALPHA,i.ONE);break;case oo:i.blendFuncSeparate(i.ZERO,i.ONE_MINUS_SRC_COLOR,i.ZERO,i.ONE);break;case lo:i.blendFunc(i.ZERO,i.SRC_COLOR);break;default:console.error("THREE.WebGLState: Invalid blending: ",D);break}p=null,y=null,S=null,P=null,T.set(0,0,0),A=0,v=D,L=jt}return}lt=lt||dt,ft=ft||X,Xt=Xt||$,(dt!==m||lt!==_)&&(i.blendEquationSeparate(Kt[dt],Kt[lt]),m=dt,_=lt),(X!==p||$!==y||ft!==S||Xt!==P)&&(i.blendFuncSeparate(Bt[X],Bt[$],Bt[ft],Bt[Xt]),p=X,y=$,S=ft,P=Xt),(he.equals(T)===!1||De!==A)&&(i.blendColor(he.r,he.g,he.b,De),T.copy(he),A=De),v=D,L=!1}function ye(D,dt){D.side===de?pt(i.CULL_FACE):it(i.CULL_FACE);let X=D.side===Pe;dt&&(X=!X),Ut(X),D.blending===Ei&&D.transparent===!1?C(Ln):C(D.blending,D.blendEquation,D.blendSrc,D.blendDst,D.blendEquationAlpha,D.blendSrcAlpha,D.blendDstAlpha,D.blendColor,D.blendAlpha,D.premultipliedAlpha),r.setFunc(D.depthFunc),r.setTest(D.depthTest),r.setMask(D.depthWrite),s.setMask(D.colorWrite);const $=D.stencilWrite;a.setTest($),$&&(a.setMask(D.stencilWriteMask),a.setFunc(D.stencilFunc,D.stencilRef,D.stencilFuncMask),a.setOp(D.stencilFail,D.stencilZFail,D.stencilZPass)),At(D.polygonOffset,D.polygonOffsetFactor,D.polygonOffsetUnits),D.alphaToCoverage===!0?it(i.SAMPLE_ALPHA_TO_COVERAGE):pt(i.SAMPLE_ALPHA_TO_COVERAGE)}function Ut(D){q!==D&&(D?i.frontFace(i.CW):i.frontFace(i.CCW),q=D)}function Gt(D){D!==bc?(it(i.CULL_FACE),D!==x&&(D===ao?i.cullFace(i.BACK):D===Tc?i.cullFace(i.FRONT):i.cullFace(i.FRONT_AND_BACK))):pt(i.CULL_FACE),x=D}function ut(D){D!==E&&(G&&i.lineWidth(D),E=D)}function At(D,dt,X){D?(it(i.POLYGON_OFFSET_FILL),(z!==dt||V!==X)&&(i.polygonOffset(dt,X),z=dt,V=X)):pt(i.POLYGON_OFFSET_FILL)}function bt(D){D?it(i.SCISSOR_TEST):pt(i.SCISSOR_TEST)}function b(D){D===void 0&&(D=i.TEXTURE0+K-1),O!==D&&(i.activeTexture(D),O=D)}function M(D,dt,X){X===void 0&&(O===null?X=i.TEXTURE0+K-1:X=O);let $=Q[X];$===void 0&&($={type:void 0,texture:void 0},Q[X]=$),($.type!==D||$.texture!==dt)&&(O!==X&&(i.activeTexture(X),O=X),i.bindTexture(D,dt||J[D]),$.type=D,$.texture=dt)}function B(){const D=Q[O];D!==void 0&&D.type!==void 0&&(i.bindTexture(D.type,null),D.type=void 0,D.texture=void 0)}function Y(){try{i.compressedTexImage2D.apply(i,arguments)}catch(D){console.error("THREE.WebGLState:",D)}}function Z(){try{i.compressedTexImage3D.apply(i,arguments)}catch(D){console.error("THREE.WebGLState:",D)}}function j(){try{i.texSubImage2D.apply(i,arguments)}catch(D){console.error("THREE.WebGLState:",D)}}function St(){try{i.texSubImage3D.apply(i,arguments)}catch(D){console.error("THREE.WebGLState:",D)}}function at(){try{i.compressedTexSubImage2D.apply(i,arguments)}catch(D){console.error("THREE.WebGLState:",D)}}function gt(){try{i.compressedTexSubImage3D.apply(i,arguments)}catch(D){console.error("THREE.WebGLState:",D)}}function qt(){try{i.texStorage2D.apply(i,arguments)}catch(D){console.error("THREE.WebGLState:",D)}}function tt(){try{i.texStorage3D.apply(i,arguments)}catch(D){console.error("THREE.WebGLState:",D)}}function _t(){try{i.texImage2D.apply(i,arguments)}catch(D){console.error("THREE.WebGLState:",D)}}function Dt(){try{i.texImage3D.apply(i,arguments)}catch(D){console.error("THREE.WebGLState:",D)}}function It(D){ht.equals(D)===!1&&(i.scissor(D.x,D.y,D.z,D.w),ht.copy(D))}function xt(D){ot.equals(D)===!1&&(i.viewport(D.x,D.y,D.z,D.w),ot.copy(D))}function Vt(D,dt){let X=l.get(dt);X===void 0&&(X=new WeakMap,l.set(dt,X));let $=X.get(D);$===void 0&&($=i.getUniformBlockIndex(dt,D.name),X.set(D,$))}function Nt(D,dt){const $=l.get(dt).get(D);o.get(dt)!==$&&(i.uniformBlockBinding(dt,$,D.__bindingPointIndex),o.set(dt,$))}function ne(){i.disable(i.BLEND),i.disable(i.CULL_FACE),i.disable(i.DEPTH_TEST),i.disable(i.POLYGON_OFFSET_FILL),i.disable(i.SCISSOR_TEST),i.disable(i.STENCIL_TEST),i.disable(i.SAMPLE_ALPHA_TO_COVERAGE),i.blendEquation(i.FUNC_ADD),i.blendFunc(i.ONE,i.ZERO),i.blendFuncSeparate(i.ONE,i.ZERO,i.ONE,i.ZERO),i.blendColor(0,0,0,0),i.colorMask(!0,!0,!0,!0),i.clearColor(0,0,0,0),i.depthMask(!0),i.depthFunc(i.LESS),i.clearDepth(1),i.stencilMask(4294967295),i.stencilFunc(i.ALWAYS,0,4294967295),i.stencilOp(i.KEEP,i.KEEP,i.KEEP),i.clearStencil(0),i.cullFace(i.BACK),i.frontFace(i.CCW),i.polygonOffset(0,0),i.activeTexture(i.TEXTURE0),i.bindFramebuffer(i.FRAMEBUFFER,null),i.bindFramebuffer(i.DRAW_FRAMEBUFFER,null),i.bindFramebuffer(i.READ_FRAMEBUFFER,null),i.useProgram(null),i.lineWidth(1),i.scissor(0,0,i.canvas.width,i.canvas.height),i.viewport(0,0,i.canvas.width,i.canvas.height),h={},O=null,Q={},d={},c=new WeakMap,u=[],f=null,g=!1,v=null,m=null,p=null,y=null,_=null,S=null,P=null,T=new Pt(0,0,0),A=0,L=!1,q=null,x=null,E=null,z=null,V=null,ht.set(0,0,i.canvas.width,i.canvas.height),ot.set(0,0,i.canvas.width,i.canvas.height),s.reset(),r.reset(),a.reset()}return{buffers:{color:s,depth:r,stencil:a},enable:it,disable:pt,bindFramebuffer:mt,drawBuffers:Tt,useProgram:kt,setBlending:C,setMaterial:ye,setFlipSided:Ut,setCullFace:Gt,setLineWidth:ut,setPolygonOffset:At,setScissorTest:bt,activeTexture:b,bindTexture:M,unbindTexture:B,compressedTexImage2D:Y,compressedTexImage3D:Z,texImage2D:_t,texImage3D:Dt,updateUBOMapping:Vt,uniformBlockBinding:Nt,texStorage2D:qt,texStorage3D:tt,texSubImage2D:j,texSubImage3D:St,compressedTexSubImage2D:at,compressedTexSubImage3D:gt,scissor:It,viewport:xt,reset:ne}}function tl(i,t,e,n){const s=Lm(n);switch(e){case Ol:return i*t;case kl:return i*t;case zl:return i*t*2;case ka:return i*t/s.components*s.byteLength;case za:return i*t/s.components*s.byteLength;case Hl:return i*t*2/s.components*s.byteLength;case Ha:return i*t*2/s.components*s.byteLength;case Bl:return i*t*3/s.components*s.byteLength;case rn:return i*t*4/s.components*s.byteLength;case Ga:return i*t*4/s.components*s.byteLength;case zs:case Hs:return Math.floor((i+3)/4)*Math.floor((t+3)/4)*8;case Gs:case Vs:return Math.floor((i+3)/4)*Math.floor((t+3)/4)*16;case aa:case la:return Math.max(i,16)*Math.max(t,8)/4;case ra:case oa:return Math.max(i,8)*Math.max(t,8)/2;case ca:case ha:return Math.floor((i+3)/4)*Math.floor((t+3)/4)*8;case ua:return Math.floor((i+3)/4)*Math.floor((t+3)/4)*16;case da:return Math.floor((i+3)/4)*Math.floor((t+3)/4)*16;case fa:return Math.floor((i+4)/5)*Math.floor((t+3)/4)*16;case pa:return Math.floor((i+4)/5)*Math.floor((t+4)/5)*16;case ma:return Math.floor((i+5)/6)*Math.floor((t+4)/5)*16;case ga:return Math.floor((i+5)/6)*Math.floor((t+5)/6)*16;case _a:return Math.floor((i+7)/8)*Math.floor((t+4)/5)*16;case xa:return Math.floor((i+7)/8)*Math.floor((t+5)/6)*16;case va:return Math.floor((i+7)/8)*Math.floor((t+7)/8)*16;case Ma:return Math.floor((i+9)/10)*Math.floor((t+4)/5)*16;case ya:return Math.floor((i+9)/10)*Math.floor((t+5)/6)*16;case Sa:return Math.floor((i+9)/10)*Math.floor((t+7)/8)*16;case wa:return Math.floor((i+9)/10)*Math.floor((t+9)/10)*16;case Ea:return Math.floor((i+11)/12)*Math.floor((t+9)/10)*16;case ba:return Math.floor((i+11)/12)*Math.floor((t+11)/12)*16;case Ws:case Ta:case Aa:return Math.ceil(i/4)*Math.ceil(t/4)*16;case Gl:case Ra:return Math.ceil(i/4)*Math.ceil(t/4)*8;case Ca:case Pa:return Math.ceil(i/4)*Math.ceil(t/4)*16}throw new Error(`Unable to determine texture byte length for ${e} format.`)}function Lm(i){switch(i){case Mn:case Ul:return{byteLength:1,components:1};case rs:case Nl:case os:return{byteLength:2,components:1};case Oa:case Ba:return{byteLength:2,components:4};case Zn:case Fa:case cn:return{byteLength:4,components:1};case Fl:return{byteLength:4,components:3}}throw new Error(`Unknown texture type ${i}.`)}function Dm(i,t,e,n,s,r,a){const o=t.has("WEBGL_multisampled_render_to_texture")?t.get("WEBGL_multisampled_render_to_texture"):null,l=typeof navigator>"u"?!1:/OculusBrowser/g.test(navigator.userAgent),h=new Ht,d=new WeakMap;let c;const u=new WeakMap;let f=!1;try{f=typeof OffscreenCanvas<"u"&&new OffscreenCanvas(1,1).getContext("2d")!==null}catch{}function g(b,M){return f?new OffscreenCanvas(b,M):Js("canvas")}function v(b,M,B){let Y=1;const Z=bt(b);if((Z.width>B||Z.height>B)&&(Y=B/Math.max(Z.width,Z.height)),Y<1)if(typeof HTMLImageElement<"u"&&b instanceof HTMLImageElement||typeof HTMLCanvasElement<"u"&&b instanceof HTMLCanvasElement||typeof ImageBitmap<"u"&&b instanceof ImageBitmap||typeof VideoFrame<"u"&&b instanceof VideoFrame){const j=Math.floor(Y*Z.width),St=Math.floor(Y*Z.height);c===void 0&&(c=g(j,St));const at=M?g(j,St):c;return at.width=j,at.height=St,at.getContext("2d").drawImage(b,0,0,j,St),console.warn("THREE.WebGLRenderer: Texture has been resized from ("+Z.width+"x"+Z.height+") to ("+j+"x"+St+")."),at}else return"data"in b&&console.warn("THREE.WebGLRenderer: Image in DataTexture is too big ("+Z.width+"x"+Z.height+")."),b;return b}function m(b){return b.generateMipmaps&&b.minFilter!==Ue&&b.minFilter!==We}function p(b){i.generateMipmap(b)}function y(b,M,B,Y,Z=!1){if(b!==null){if(i[b]!==void 0)return i[b];console.warn("THREE.WebGLRenderer: Attempt to use non-existing WebGL internal format '"+b+"'")}let j=M;if(M===i.RED&&(B===i.FLOAT&&(j=i.R32F),B===i.HALF_FLOAT&&(j=i.R16F),B===i.UNSIGNED_BYTE&&(j=i.R8)),M===i.RED_INTEGER&&(B===i.UNSIGNED_BYTE&&(j=i.R8UI),B===i.UNSIGNED_SHORT&&(j=i.R16UI),B===i.UNSIGNED_INT&&(j=i.R32UI),B===i.BYTE&&(j=i.R8I),B===i.SHORT&&(j=i.R16I),B===i.INT&&(j=i.R32I)),M===i.RG&&(B===i.FLOAT&&(j=i.RG32F),B===i.HALF_FLOAT&&(j=i.RG16F),B===i.UNSIGNED_BYTE&&(j=i.RG8)),M===i.RG_INTEGER&&(B===i.UNSIGNED_BYTE&&(j=i.RG8UI),B===i.UNSIGNED_SHORT&&(j=i.RG16UI),B===i.UNSIGNED_INT&&(j=i.RG32UI),B===i.BYTE&&(j=i.RG8I),B===i.SHORT&&(j=i.RG16I),B===i.INT&&(j=i.RG32I)),M===i.RGB_INTEGER&&(B===i.UNSIGNED_BYTE&&(j=i.RGB8UI),B===i.UNSIGNED_SHORT&&(j=i.RGB16UI),B===i.UNSIGNED_INT&&(j=i.RGB32UI),B===i.BYTE&&(j=i.RGB8I),B===i.SHORT&&(j=i.RGB16I),B===i.INT&&(j=i.RGB32I)),M===i.RGBA_INTEGER&&(B===i.UNSIGNED_BYTE&&(j=i.RGBA8UI),B===i.UNSIGNED_SHORT&&(j=i.RGBA16UI),B===i.UNSIGNED_INT&&(j=i.RGBA32UI),B===i.BYTE&&(j=i.RGBA8I),B===i.SHORT&&(j=i.RGBA16I),B===i.INT&&(j=i.RGBA32I)),M===i.RGB&&B===i.UNSIGNED_INT_5_9_9_9_REV&&(j=i.RGB9_E5),M===i.RGBA){const St=Z?Ks:Jt.getTransfer(Y);B===i.FLOAT&&(j=i.RGBA32F),B===i.HALF_FLOAT&&(j=i.RGBA16F),B===i.UNSIGNED_BYTE&&(j=St===se?i.SRGB8_ALPHA8:i.RGBA8),B===i.UNSIGNED_SHORT_4_4_4_4&&(j=i.RGBA4),B===i.UNSIGNED_SHORT_5_5_5_1&&(j=i.RGB5_A1)}return(j===i.R16F||j===i.R32F||j===i.RG16F||j===i.RG32F||j===i.RGBA16F||j===i.RGBA32F)&&t.get("EXT_color_buffer_float"),j}function _(b,M){let B;return b?M===null||M===Zn||M===Li?B=i.DEPTH24_STENCIL8:M===cn?B=i.DEPTH32F_STENCIL8:M===rs&&(B=i.DEPTH24_STENCIL8,console.warn("DepthTexture: 16 bit depth attachment is not supported with stencil. Using 24-bit attachment.")):M===null||M===Zn||M===Li?B=i.DEPTH_COMPONENT24:M===cn?B=i.DEPTH_COMPONENT32F:M===rs&&(B=i.DEPTH_COMPONENT16),B}function S(b,M){return m(b)===!0||b.isFramebufferTexture&&b.minFilter!==Ue&&b.minFilter!==We?Math.log2(Math.max(M.width,M.height))+1:b.mipmaps!==void 0&&b.mipmaps.length>0?b.mipmaps.length:b.isCompressedTexture&&Array.isArray(b.image)?M.mipmaps.length:1}function P(b){const M=b.target;M.removeEventListener("dispose",P),A(M),M.isVideoTexture&&d.delete(M)}function T(b){const M=b.target;M.removeEventListener("dispose",T),q(M)}function A(b){const M=n.get(b);if(M.__webglInit===void 0)return;const B=b.source,Y=u.get(B);if(Y){const Z=Y[M.__cacheKey];Z.usedTimes--,Z.usedTimes===0&&L(b),Object.keys(Y).length===0&&u.delete(B)}n.remove(b)}function L(b){const M=n.get(b);i.deleteTexture(M.__webglTexture);const B=b.source,Y=u.get(B);delete Y[M.__cacheKey],a.memory.textures--}function q(b){const M=n.get(b);if(b.depthTexture&&b.depthTexture.dispose(),b.isWebGLCubeRenderTarget)for(let Y=0;Y<6;Y++){if(Array.isArray(M.__webglFramebuffer[Y]))for(let Z=0;Z<M.__webglFramebuffer[Y].length;Z++)i.deleteFramebuffer(M.__webglFramebuffer[Y][Z]);else i.deleteFramebuffer(M.__webglFramebuffer[Y]);M.__webglDepthbuffer&&i.deleteRenderbuffer(M.__webglDepthbuffer[Y])}else{if(Array.isArray(M.__webglFramebuffer))for(let Y=0;Y<M.__webglFramebuffer.length;Y++)i.deleteFramebuffer(M.__webglFramebuffer[Y]);else i.deleteFramebuffer(M.__webglFramebuffer);if(M.__webglDepthbuffer&&i.deleteRenderbuffer(M.__webglDepthbuffer),M.__webglMultisampledFramebuffer&&i.deleteFramebuffer(M.__webglMultisampledFramebuffer),M.__webglColorRenderbuffer)for(let Y=0;Y<M.__webglColorRenderbuffer.length;Y++)M.__webglColorRenderbuffer[Y]&&i.deleteRenderbuffer(M.__webglColorRenderbuffer[Y]);M.__webglDepthRenderbuffer&&i.deleteRenderbuffer(M.__webglDepthRenderbuffer)}const B=b.textures;for(let Y=0,Z=B.length;Y<Z;Y++){const j=n.get(B[Y]);j.__webglTexture&&(i.deleteTexture(j.__webglTexture),a.memory.textures--),n.remove(B[Y])}n.remove(b)}let x=0;function E(){x=0}function z(){const b=x;return b>=s.maxTextures&&console.warn("THREE.WebGLTextures: Trying to use "+b+" texture units while this GPU supports only "+s.maxTextures),x+=1,b}function V(b){const M=[];return M.push(b.wrapS),M.push(b.wrapT),M.push(b.wrapR||0),M.push(b.magFilter),M.push(b.minFilter),M.push(b.anisotropy),M.push(b.internalFormat),M.push(b.format),M.push(b.type),M.push(b.generateMipmaps),M.push(b.premultiplyAlpha),M.push(b.flipY),M.push(b.unpackAlignment),M.push(b.colorSpace),M.join()}function K(b,M){const B=n.get(b);if(b.isVideoTexture&&ut(b),b.isRenderTargetTexture===!1&&b.version>0&&B.__version!==b.version){const Y=b.image;if(Y===null)console.warn("THREE.WebGLRenderer: Texture marked for update but no image data found.");else if(Y.complete===!1)console.warn("THREE.WebGLRenderer: Texture marked for update but image is incomplete");else{ot(B,b,M);return}}e.bindTexture(i.TEXTURE_2D,B.__webglTexture,i.TEXTURE0+M)}function G(b,M){const B=n.get(b);if(b.version>0&&B.__version!==b.version){ot(B,b,M);return}e.bindTexture(i.TEXTURE_2D_ARRAY,B.__webglTexture,i.TEXTURE0+M)}function I(b,M){const B=n.get(b);if(b.version>0&&B.__version!==b.version){ot(B,b,M);return}e.bindTexture(i.TEXTURE_3D,B.__webglTexture,i.TEXTURE0+M)}function F(b,M){const B=n.get(b);if(b.version>0&&B.__version!==b.version){W(B,b,M);return}e.bindTexture(i.TEXTURE_CUBE_MAP,B.__webglTexture,i.TEXTURE0+M)}const O={[ss]:i.REPEAT,[xn]:i.CLAMP_TO_EDGE,[sa]:i.MIRRORED_REPEAT},Q={[Ue]:i.NEAREST,[th]:i.NEAREST_MIPMAP_NEAREST,[ds]:i.NEAREST_MIPMAP_LINEAR,[We]:i.LINEAR,[dr]:i.LINEAR_MIPMAP_NEAREST,[jn]:i.LINEAR_MIPMAP_LINEAR},nt={[sh]:i.NEVER,[hh]:i.ALWAYS,[rh]:i.LESS,[Wl]:i.LEQUAL,[ah]:i.EQUAL,[ch]:i.GEQUAL,[oh]:i.GREATER,[lh]:i.NOTEQUAL};function rt(b,M){if(M.type===cn&&t.has("OES_texture_float_linear")===!1&&(M.magFilter===We||M.magFilter===dr||M.magFilter===ds||M.magFilter===jn||M.minFilter===We||M.minFilter===dr||M.minFilter===ds||M.minFilter===jn)&&console.warn("THREE.WebGLRenderer: Unable to use linear filtering with floating point textures. OES_texture_float_linear not supported on this device."),i.texParameteri(b,i.TEXTURE_WRAP_S,O[M.wrapS]),i.texParameteri(b,i.TEXTURE_WRAP_T,O[M.wrapT]),(b===i.TEXTURE_3D||b===i.TEXTURE_2D_ARRAY)&&i.texParameteri(b,i.TEXTURE_WRAP_R,O[M.wrapR]),i.texParameteri(b,i.TEXTURE_MAG_FILTER,Q[M.magFilter]),i.texParameteri(b,i.TEXTURE_MIN_FILTER,Q[M.minFilter]),M.compareFunction&&(i.texParameteri(b,i.TEXTURE_COMPARE_MODE,i.COMPARE_REF_TO_TEXTURE),i.texParameteri(b,i.TEXTURE_COMPARE_FUNC,nt[M.compareFunction])),t.has("EXT_texture_filter_anisotropic")===!0){if(M.magFilter===Ue||M.minFilter!==ds&&M.minFilter!==jn||M.type===cn&&t.has("OES_texture_float_linear")===!1)return;if(M.anisotropy>1||n.get(M).__currentAnisotropy){const B=t.get("EXT_texture_filter_anisotropic");i.texParameterf(b,B.TEXTURE_MAX_ANISOTROPY_EXT,Math.min(M.anisotropy,s.getMaxAnisotropy())),n.get(M).__currentAnisotropy=M.anisotropy}}}function ht(b,M){let B=!1;b.__webglInit===void 0&&(b.__webglInit=!0,M.addEventListener("dispose",P));const Y=M.source;let Z=u.get(Y);Z===void 0&&(Z={},u.set(Y,Z));const j=V(M);if(j!==b.__cacheKey){Z[j]===void 0&&(Z[j]={texture:i.createTexture(),usedTimes:0},a.memory.textures++,B=!0),Z[j].usedTimes++;const St=Z[b.__cacheKey];St!==void 0&&(Z[b.__cacheKey].usedTimes--,St.usedTimes===0&&L(M)),b.__cacheKey=j,b.__webglTexture=Z[j].texture}return B}function ot(b,M,B){let Y=i.TEXTURE_2D;(M.isDataArrayTexture||M.isCompressedArrayTexture)&&(Y=i.TEXTURE_2D_ARRAY),M.isData3DTexture&&(Y=i.TEXTURE_3D);const Z=ht(b,M),j=M.source;e.bindTexture(Y,b.__webglTexture,i.TEXTURE0+B);const St=n.get(j);if(j.version!==St.__version||Z===!0){e.activeTexture(i.TEXTURE0+B);const at=Jt.getPrimaries(Jt.workingColorSpace),gt=M.colorSpace===Cn?null:Jt.getPrimaries(M.colorSpace),qt=M.colorSpace===Cn||at===gt?i.NONE:i.BROWSER_DEFAULT_WEBGL;i.pixelStorei(i.UNPACK_FLIP_Y_WEBGL,M.flipY),i.pixelStorei(i.UNPACK_PREMULTIPLY_ALPHA_WEBGL,M.premultiplyAlpha),i.pixelStorei(i.UNPACK_ALIGNMENT,M.unpackAlignment),i.pixelStorei(i.UNPACK_COLORSPACE_CONVERSION_WEBGL,qt);let tt=v(M.image,!1,s.maxTextureSize);tt=At(M,tt);const _t=r.convert(M.format,M.colorSpace),Dt=r.convert(M.type);let It=y(M.internalFormat,_t,Dt,M.colorSpace,M.isVideoTexture);rt(Y,M);let xt;const Vt=M.mipmaps,Nt=M.isVideoTexture!==!0,ne=St.__version===void 0||Z===!0,D=j.dataReady,dt=S(M,tt);if(M.isDepthTexture)It=_(M.format===Di,M.type),ne&&(Nt?e.texStorage2D(i.TEXTURE_2D,1,It,tt.width,tt.height):e.texImage2D(i.TEXTURE_2D,0,It,tt.width,tt.height,0,_t,Dt,null));else if(M.isDataTexture)if(Vt.length>0){Nt&&ne&&e.texStorage2D(i.TEXTURE_2D,dt,It,Vt[0].width,Vt[0].height);for(let X=0,$=Vt.length;X<$;X++)xt=Vt[X],Nt?D&&e.texSubImage2D(i.TEXTURE_2D,X,0,0,xt.width,xt.height,_t,Dt,xt.data):e.texImage2D(i.TEXTURE_2D,X,It,xt.width,xt.height,0,_t,Dt,xt.data);M.generateMipmaps=!1}else Nt?(ne&&e.texStorage2D(i.TEXTURE_2D,dt,It,tt.width,tt.height),D&&e.texSubImage2D(i.TEXTURE_2D,0,0,0,tt.width,tt.height,_t,Dt,tt.data)):e.texImage2D(i.TEXTURE_2D,0,It,tt.width,tt.height,0,_t,Dt,tt.data);else if(M.isCompressedTexture)if(M.isCompressedArrayTexture){Nt&&ne&&e.texStorage3D(i.TEXTURE_2D_ARRAY,dt,It,Vt[0].width,Vt[0].height,tt.depth);for(let X=0,$=Vt.length;X<$;X++)if(xt=Vt[X],M.format!==rn)if(_t!==null)if(Nt){if(D)if(M.layerUpdates.size>0){const lt=tl(xt.width,xt.height,M.format,M.type);for(const ft of M.layerUpdates){const Xt=xt.data.subarray(ft*lt/xt.data.BYTES_PER_ELEMENT,(ft+1)*lt/xt.data.BYTES_PER_ELEMENT);e.compressedTexSubImage3D(i.TEXTURE_2D_ARRAY,X,0,0,ft,xt.width,xt.height,1,_t,Xt,0,0)}M.clearLayerUpdates()}else e.compressedTexSubImage3D(i.TEXTURE_2D_ARRAY,X,0,0,0,xt.width,xt.height,tt.depth,_t,xt.data,0,0)}else e.compressedTexImage3D(i.TEXTURE_2D_ARRAY,X,It,xt.width,xt.height,tt.depth,0,xt.data,0,0);else console.warn("THREE.WebGLRenderer: Attempt to load unsupported compressed texture format in .uploadTexture()");else Nt?D&&e.texSubImage3D(i.TEXTURE_2D_ARRAY,X,0,0,0,xt.width,xt.height,tt.depth,_t,Dt,xt.data):e.texImage3D(i.TEXTURE_2D_ARRAY,X,It,xt.width,xt.height,tt.depth,0,_t,Dt,xt.data)}else{Nt&&ne&&e.texStorage2D(i.TEXTURE_2D,dt,It,Vt[0].width,Vt[0].height);for(let X=0,$=Vt.length;X<$;X++)xt=Vt[X],M.format!==rn?_t!==null?Nt?D&&e.compressedTexSubImage2D(i.TEXTURE_2D,X,0,0,xt.width,xt.height,_t,xt.data):e.compressedTexImage2D(i.TEXTURE_2D,X,It,xt.width,xt.height,0,xt.data):console.warn("THREE.WebGLRenderer: Attempt to load unsupported compressed texture format in .uploadTexture()"):Nt?D&&e.texSubImage2D(i.TEXTURE_2D,X,0,0,xt.width,xt.height,_t,Dt,xt.data):e.texImage2D(i.TEXTURE_2D,X,It,xt.width,xt.height,0,_t,Dt,xt.data)}else if(M.isDataArrayTexture)if(Nt){if(ne&&e.texStorage3D(i.TEXTURE_2D_ARRAY,dt,It,tt.width,tt.height,tt.depth),D)if(M.layerUpdates.size>0){const X=tl(tt.width,tt.height,M.format,M.type);for(const $ of M.layerUpdates){const lt=tt.data.subarray($*X/tt.data.BYTES_PER_ELEMENT,($+1)*X/tt.data.BYTES_PER_ELEMENT);e.texSubImage3D(i.TEXTURE_2D_ARRAY,0,0,0,$,tt.width,tt.height,1,_t,Dt,lt)}M.clearLayerUpdates()}else e.texSubImage3D(i.TEXTURE_2D_ARRAY,0,0,0,0,tt.width,tt.height,tt.depth,_t,Dt,tt.data)}else e.texImage3D(i.TEXTURE_2D_ARRAY,0,It,tt.width,tt.height,tt.depth,0,_t,Dt,tt.data);else if(M.isData3DTexture)Nt?(ne&&e.texStorage3D(i.TEXTURE_3D,dt,It,tt.width,tt.height,tt.depth),D&&e.texSubImage3D(i.TEXTURE_3D,0,0,0,0,tt.width,tt.height,tt.depth,_t,Dt,tt.data)):e.texImage3D(i.TEXTURE_3D,0,It,tt.width,tt.height,tt.depth,0,_t,Dt,tt.data);else if(M.isFramebufferTexture){if(ne)if(Nt)e.texStorage2D(i.TEXTURE_2D,dt,It,tt.width,tt.height);else{let X=tt.width,$=tt.height;for(let lt=0;lt<dt;lt++)e.texImage2D(i.TEXTURE_2D,lt,It,X,$,0,_t,Dt,null),X>>=1,$>>=1}}else if(Vt.length>0){if(Nt&&ne){const X=bt(Vt[0]);e.texStorage2D(i.TEXTURE_2D,dt,It,X.width,X.height)}for(let X=0,$=Vt.length;X<$;X++)xt=Vt[X],Nt?D&&e.texSubImage2D(i.TEXTURE_2D,X,0,0,_t,Dt,xt):e.texImage2D(i.TEXTURE_2D,X,It,_t,Dt,xt);M.generateMipmaps=!1}else if(Nt){if(ne){const X=bt(tt);e.texStorage2D(i.TEXTURE_2D,dt,It,X.width,X.height)}D&&e.texSubImage2D(i.TEXTURE_2D,0,0,0,_t,Dt,tt)}else e.texImage2D(i.TEXTURE_2D,0,It,_t,Dt,tt);m(M)&&p(Y),St.__version=j.version,M.onUpdate&&M.onUpdate(M)}b.__version=M.version}function W(b,M,B){if(M.image.length!==6)return;const Y=ht(b,M),Z=M.source;e.bindTexture(i.TEXTURE_CUBE_MAP,b.__webglTexture,i.TEXTURE0+B);const j=n.get(Z);if(Z.version!==j.__version||Y===!0){e.activeTexture(i.TEXTURE0+B);const St=Jt.getPrimaries(Jt.workingColorSpace),at=M.colorSpace===Cn?null:Jt.getPrimaries(M.colorSpace),gt=M.colorSpace===Cn||St===at?i.NONE:i.BROWSER_DEFAULT_WEBGL;i.pixelStorei(i.UNPACK_FLIP_Y_WEBGL,M.flipY),i.pixelStorei(i.UNPACK_PREMULTIPLY_ALPHA_WEBGL,M.premultiplyAlpha),i.pixelStorei(i.UNPACK_ALIGNMENT,M.unpackAlignment),i.pixelStorei(i.UNPACK_COLORSPACE_CONVERSION_WEBGL,gt);const qt=M.isCompressedTexture||M.image[0].isCompressedTexture,tt=M.image[0]&&M.image[0].isDataTexture,_t=[];for(let $=0;$<6;$++)!qt&&!tt?_t[$]=v(M.image[$],!0,s.maxCubemapSize):_t[$]=tt?M.image[$].image:M.image[$],_t[$]=At(M,_t[$]);const Dt=_t[0],It=r.convert(M.format,M.colorSpace),xt=r.convert(M.type),Vt=y(M.internalFormat,It,xt,M.colorSpace),Nt=M.isVideoTexture!==!0,ne=j.__version===void 0||Y===!0,D=Z.dataReady;let dt=S(M,Dt);rt(i.TEXTURE_CUBE_MAP,M);let X;if(qt){Nt&&ne&&e.texStorage2D(i.TEXTURE_CUBE_MAP,dt,Vt,Dt.width,Dt.height);for(let $=0;$<6;$++){X=_t[$].mipmaps;for(let lt=0;lt<X.length;lt++){const ft=X[lt];M.format!==rn?It!==null?Nt?D&&e.compressedTexSubImage2D(i.TEXTURE_CUBE_MAP_POSITIVE_X+$,lt,0,0,ft.width,ft.height,It,ft.data):e.compressedTexImage2D(i.TEXTURE_CUBE_MAP_POSITIVE_X+$,lt,Vt,ft.width,ft.height,0,ft.data):console.warn("THREE.WebGLRenderer: Attempt to load unsupported compressed texture format in .setTextureCube()"):Nt?D&&e.texSubImage2D(i.TEXTURE_CUBE_MAP_POSITIVE_X+$,lt,0,0,ft.width,ft.height,It,xt,ft.data):e.texImage2D(i.TEXTURE_CUBE_MAP_POSITIVE_X+$,lt,Vt,ft.width,ft.height,0,It,xt,ft.data)}}}else{if(X=M.mipmaps,Nt&&ne){X.length>0&&dt++;const $=bt(_t[0]);e.texStorage2D(i.TEXTURE_CUBE_MAP,dt,Vt,$.width,$.height)}for(let $=0;$<6;$++)if(tt){Nt?D&&e.texSubImage2D(i.TEXTURE_CUBE_MAP_POSITIVE_X+$,0,0,0,_t[$].width,_t[$].height,It,xt,_t[$].data):e.texImage2D(i.TEXTURE_CUBE_MAP_POSITIVE_X+$,0,Vt,_t[$].width,_t[$].height,0,It,xt,_t[$].data);for(let lt=0;lt<X.length;lt++){const Xt=X[lt].image[$].image;Nt?D&&e.texSubImage2D(i.TEXTURE_CUBE_MAP_POSITIVE_X+$,lt+1,0,0,Xt.width,Xt.height,It,xt,Xt.data):e.texImage2D(i.TEXTURE_CUBE_MAP_POSITIVE_X+$,lt+1,Vt,Xt.width,Xt.height,0,It,xt,Xt.data)}}else{Nt?D&&e.texSubImage2D(i.TEXTURE_CUBE_MAP_POSITIVE_X+$,0,0,0,It,xt,_t[$]):e.texImage2D(i.TEXTURE_CUBE_MAP_POSITIVE_X+$,0,Vt,It,xt,_t[$]);for(let lt=0;lt<X.length;lt++){const ft=X[lt];Nt?D&&e.texSubImage2D(i.TEXTURE_CUBE_MAP_POSITIVE_X+$,lt+1,0,0,It,xt,ft.image[$]):e.texImage2D(i.TEXTURE_CUBE_MAP_POSITIVE_X+$,lt+1,Vt,It,xt,ft.image[$])}}}m(M)&&p(i.TEXTURE_CUBE_MAP),j.__version=Z.version,M.onUpdate&&M.onUpdate(M)}b.__version=M.version}function J(b,M,B,Y,Z,j){const St=r.convert(B.format,B.colorSpace),at=r.convert(B.type),gt=y(B.internalFormat,St,at,B.colorSpace);if(!n.get(M).__hasExternalTextures){const tt=Math.max(1,M.width>>j),_t=Math.max(1,M.height>>j);Z===i.TEXTURE_3D||Z===i.TEXTURE_2D_ARRAY?e.texImage3D(Z,j,gt,tt,_t,M.depth,0,St,at,null):e.texImage2D(Z,j,gt,tt,_t,0,St,at,null)}e.bindFramebuffer(i.FRAMEBUFFER,b),Gt(M)?o.framebufferTexture2DMultisampleEXT(i.FRAMEBUFFER,Y,Z,n.get(B).__webglTexture,0,Ut(M)):(Z===i.TEXTURE_2D||Z>=i.TEXTURE_CUBE_MAP_POSITIVE_X&&Z<=i.TEXTURE_CUBE_MAP_NEGATIVE_Z)&&i.framebufferTexture2D(i.FRAMEBUFFER,Y,Z,n.get(B).__webglTexture,j),e.bindFramebuffer(i.FRAMEBUFFER,null)}function it(b,M,B){if(i.bindRenderbuffer(i.RENDERBUFFER,b),M.depthBuffer){const Y=M.depthTexture,Z=Y&&Y.isDepthTexture?Y.type:null,j=_(M.stencilBuffer,Z),St=M.stencilBuffer?i.DEPTH_STENCIL_ATTACHMENT:i.DEPTH_ATTACHMENT,at=Ut(M);Gt(M)?o.renderbufferStorageMultisampleEXT(i.RENDERBUFFER,at,j,M.width,M.height):B?i.renderbufferStorageMultisample(i.RENDERBUFFER,at,j,M.width,M.height):i.renderbufferStorage(i.RENDERBUFFER,j,M.width,M.height),i.framebufferRenderbuffer(i.FRAMEBUFFER,St,i.RENDERBUFFER,b)}else{const Y=M.textures;for(let Z=0;Z<Y.length;Z++){const j=Y[Z],St=r.convert(j.format,j.colorSpace),at=r.convert(j.type),gt=y(j.internalFormat,St,at,j.colorSpace),qt=Ut(M);B&&Gt(M)===!1?i.renderbufferStorageMultisample(i.RENDERBUFFER,qt,gt,M.width,M.height):Gt(M)?o.renderbufferStorageMultisampleEXT(i.RENDERBUFFER,qt,gt,M.width,M.height):i.renderbufferStorage(i.RENDERBUFFER,gt,M.width,M.height)}}i.bindRenderbuffer(i.RENDERBUFFER,null)}function pt(b,M){if(M&&M.isWebGLCubeRenderTarget)throw new Error("Depth Texture with cube render targets is not supported");if(e.bindFramebuffer(i.FRAMEBUFFER,b),!(M.depthTexture&&M.depthTexture.isDepthTexture))throw new Error("renderTarget.depthTexture must be an instance of THREE.DepthTexture");(!n.get(M.depthTexture).__webglTexture||M.depthTexture.image.width!==M.width||M.depthTexture.image.height!==M.height)&&(M.depthTexture.image.width=M.width,M.depthTexture.image.height=M.height,M.depthTexture.needsUpdate=!0),K(M.depthTexture,0);const Y=n.get(M.depthTexture).__webglTexture,Z=Ut(M);if(M.depthTexture.format===bi)Gt(M)?o.framebufferTexture2DMultisampleEXT(i.FRAMEBUFFER,i.DEPTH_ATTACHMENT,i.TEXTURE_2D,Y,0,Z):i.framebufferTexture2D(i.FRAMEBUFFER,i.DEPTH_ATTACHMENT,i.TEXTURE_2D,Y,0);else if(M.depthTexture.format===Di)Gt(M)?o.framebufferTexture2DMultisampleEXT(i.FRAMEBUFFER,i.DEPTH_STENCIL_ATTACHMENT,i.TEXTURE_2D,Y,0,Z):i.framebufferTexture2D(i.FRAMEBUFFER,i.DEPTH_STENCIL_ATTACHMENT,i.TEXTURE_2D,Y,0);else throw new Error("Unknown depthTexture format")}function mt(b){const M=n.get(b),B=b.isWebGLCubeRenderTarget===!0;if(M.__boundDepthTexture!==b.depthTexture){const Y=b.depthTexture;if(M.__depthDisposeCallback&&M.__depthDisposeCallback(),Y){const Z=()=>{delete M.__boundDepthTexture,delete M.__depthDisposeCallback,Y.removeEventListener("dispose",Z)};Y.addEventListener("dispose",Z),M.__depthDisposeCallback=Z}M.__boundDepthTexture=Y}if(b.depthTexture&&!M.__autoAllocateDepthBuffer){if(B)throw new Error("target.depthTexture not supported in Cube render targets");pt(M.__webglFramebuffer,b)}else if(B){M.__webglDepthbuffer=[];for(let Y=0;Y<6;Y++)if(e.bindFramebuffer(i.FRAMEBUFFER,M.__webglFramebuffer[Y]),M.__webglDepthbuffer[Y]===void 0)M.__webglDepthbuffer[Y]=i.createRenderbuffer(),it(M.__webglDepthbuffer[Y],b,!1);else{const Z=b.stencilBuffer?i.DEPTH_STENCIL_ATTACHMENT:i.DEPTH_ATTACHMENT,j=M.__webglDepthbuffer[Y];i.bindRenderbuffer(i.RENDERBUFFER,j),i.framebufferRenderbuffer(i.FRAMEBUFFER,Z,i.RENDERBUFFER,j)}}else if(e.bindFramebuffer(i.FRAMEBUFFER,M.__webglFramebuffer),M.__webglDepthbuffer===void 0)M.__webglDepthbuffer=i.createRenderbuffer(),it(M.__webglDepthbuffer,b,!1);else{const Y=b.stencilBuffer?i.DEPTH_STENCIL_ATTACHMENT:i.DEPTH_ATTACHMENT,Z=M.__webglDepthbuffer;i.bindRenderbuffer(i.RENDERBUFFER,Z),i.framebufferRenderbuffer(i.FRAMEBUFFER,Y,i.RENDERBUFFER,Z)}e.bindFramebuffer(i.FRAMEBUFFER,null)}function Tt(b,M,B){const Y=n.get(b);M!==void 0&&J(Y.__webglFramebuffer,b,b.texture,i.COLOR_ATTACHMENT0,i.TEXTURE_2D,0),B!==void 0&&mt(b)}function kt(b){const M=b.texture,B=n.get(b),Y=n.get(M);b.addEventListener("dispose",T);const Z=b.textures,j=b.isWebGLCubeRenderTarget===!0,St=Z.length>1;if(St||(Y.__webglTexture===void 0&&(Y.__webglTexture=i.createTexture()),Y.__version=M.version,a.memory.textures++),j){B.__webglFramebuffer=[];for(let at=0;at<6;at++)if(M.mipmaps&&M.mipmaps.length>0){B.__webglFramebuffer[at]=[];for(let gt=0;gt<M.mipmaps.length;gt++)B.__webglFramebuffer[at][gt]=i.createFramebuffer()}else B.__webglFramebuffer[at]=i.createFramebuffer()}else{if(M.mipmaps&&M.mipmaps.length>0){B.__webglFramebuffer=[];for(let at=0;at<M.mipmaps.length;at++)B.__webglFramebuffer[at]=i.createFramebuffer()}else B.__webglFramebuffer=i.createFramebuffer();if(St)for(let at=0,gt=Z.length;at<gt;at++){const qt=n.get(Z[at]);qt.__webglTexture===void 0&&(qt.__webglTexture=i.createTexture(),a.memory.textures++)}if(b.samples>0&&Gt(b)===!1){B.__webglMultisampledFramebuffer=i.createFramebuffer(),B.__webglColorRenderbuffer=[],e.bindFramebuffer(i.FRAMEBUFFER,B.__webglMultisampledFramebuffer);for(let at=0;at<Z.length;at++){const gt=Z[at];B.__webglColorRenderbuffer[at]=i.createRenderbuffer(),i.bindRenderbuffer(i.RENDERBUFFER,B.__webglColorRenderbuffer[at]);const qt=r.convert(gt.format,gt.colorSpace),tt=r.convert(gt.type),_t=y(gt.internalFormat,qt,tt,gt.colorSpace,b.isXRRenderTarget===!0),Dt=Ut(b);i.renderbufferStorageMultisample(i.RENDERBUFFER,Dt,_t,b.width,b.height),i.framebufferRenderbuffer(i.FRAMEBUFFER,i.COLOR_ATTACHMENT0+at,i.RENDERBUFFER,B.__webglColorRenderbuffer[at])}i.bindRenderbuffer(i.RENDERBUFFER,null),b.depthBuffer&&(B.__webglDepthRenderbuffer=i.createRenderbuffer(),it(B.__webglDepthRenderbuffer,b,!0)),e.bindFramebuffer(i.FRAMEBUFFER,null)}}if(j){e.bindTexture(i.TEXTURE_CUBE_MAP,Y.__webglTexture),rt(i.TEXTURE_CUBE_MAP,M);for(let at=0;at<6;at++)if(M.mipmaps&&M.mipmaps.length>0)for(let gt=0;gt<M.mipmaps.length;gt++)J(B.__webglFramebuffer[at][gt],b,M,i.COLOR_ATTACHMENT0,i.TEXTURE_CUBE_MAP_POSITIVE_X+at,gt);else J(B.__webglFramebuffer[at],b,M,i.COLOR_ATTACHMENT0,i.TEXTURE_CUBE_MAP_POSITIVE_X+at,0);m(M)&&p(i.TEXTURE_CUBE_MAP),e.unbindTexture()}else if(St){for(let at=0,gt=Z.length;at<gt;at++){const qt=Z[at],tt=n.get(qt);e.bindTexture(i.TEXTURE_2D,tt.__webglTexture),rt(i.TEXTURE_2D,qt),J(B.__webglFramebuffer,b,qt,i.COLOR_ATTACHMENT0+at,i.TEXTURE_2D,0),m(qt)&&p(i.TEXTURE_2D)}e.unbindTexture()}else{let at=i.TEXTURE_2D;if((b.isWebGL3DRenderTarget||b.isWebGLArrayRenderTarget)&&(at=b.isWebGL3DRenderTarget?i.TEXTURE_3D:i.TEXTURE_2D_ARRAY),e.bindTexture(at,Y.__webglTexture),rt(at,M),M.mipmaps&&M.mipmaps.length>0)for(let gt=0;gt<M.mipmaps.length;gt++)J(B.__webglFramebuffer[gt],b,M,i.COLOR_ATTACHMENT0,at,gt);else J(B.__webglFramebuffer,b,M,i.COLOR_ATTACHMENT0,at,0);m(M)&&p(at),e.unbindTexture()}b.depthBuffer&&mt(b)}function Kt(b){const M=b.textures;for(let B=0,Y=M.length;B<Y;B++){const Z=M[B];if(m(Z)){const j=b.isWebGLCubeRenderTarget?i.TEXTURE_CUBE_MAP:i.TEXTURE_2D,St=n.get(Z).__webglTexture;e.bindTexture(j,St),p(j),e.unbindTexture()}}}const Bt=[],C=[];function ye(b){if(b.samples>0){if(Gt(b)===!1){const M=b.textures,B=b.width,Y=b.height;let Z=i.COLOR_BUFFER_BIT;const j=b.stencilBuffer?i.DEPTH_STENCIL_ATTACHMENT:i.DEPTH_ATTACHMENT,St=n.get(b),at=M.length>1;if(at)for(let gt=0;gt<M.length;gt++)e.bindFramebuffer(i.FRAMEBUFFER,St.__webglMultisampledFramebuffer),i.framebufferRenderbuffer(i.FRAMEBUFFER,i.COLOR_ATTACHMENT0+gt,i.RENDERBUFFER,null),e.bindFramebuffer(i.FRAMEBUFFER,St.__webglFramebuffer),i.framebufferTexture2D(i.DRAW_FRAMEBUFFER,i.COLOR_ATTACHMENT0+gt,i.TEXTURE_2D,null,0);e.bindFramebuffer(i.READ_FRAMEBUFFER,St.__webglMultisampledFramebuffer),e.bindFramebuffer(i.DRAW_FRAMEBUFFER,St.__webglFramebuffer);for(let gt=0;gt<M.length;gt++){if(b.resolveDepthBuffer&&(b.depthBuffer&&(Z|=i.DEPTH_BUFFER_BIT),b.stencilBuffer&&b.resolveStencilBuffer&&(Z|=i.STENCIL_BUFFER_BIT)),at){i.framebufferRenderbuffer(i.READ_FRAMEBUFFER,i.COLOR_ATTACHMENT0,i.RENDERBUFFER,St.__webglColorRenderbuffer[gt]);const qt=n.get(M[gt]).__webglTexture;i.framebufferTexture2D(i.DRAW_FRAMEBUFFER,i.COLOR_ATTACHMENT0,i.TEXTURE_2D,qt,0)}i.blitFramebuffer(0,0,B,Y,0,0,B,Y,Z,i.NEAREST),l===!0&&(Bt.length=0,C.length=0,Bt.push(i.COLOR_ATTACHMENT0+gt),b.depthBuffer&&b.resolveDepthBuffer===!1&&(Bt.push(j),C.push(j),i.invalidateFramebuffer(i.DRAW_FRAMEBUFFER,C)),i.invalidateFramebuffer(i.READ_FRAMEBUFFER,Bt))}if(e.bindFramebuffer(i.READ_FRAMEBUFFER,null),e.bindFramebuffer(i.DRAW_FRAMEBUFFER,null),at)for(let gt=0;gt<M.length;gt++){e.bindFramebuffer(i.FRAMEBUFFER,St.__webglMultisampledFramebuffer),i.framebufferRenderbuffer(i.FRAMEBUFFER,i.COLOR_ATTACHMENT0+gt,i.RENDERBUFFER,St.__webglColorRenderbuffer[gt]);const qt=n.get(M[gt]).__webglTexture;e.bindFramebuffer(i.FRAMEBUFFER,St.__webglFramebuffer),i.framebufferTexture2D(i.DRAW_FRAMEBUFFER,i.COLOR_ATTACHMENT0+gt,i.TEXTURE_2D,qt,0)}e.bindFramebuffer(i.DRAW_FRAMEBUFFER,St.__webglMultisampledFramebuffer)}else if(b.depthBuffer&&b.resolveDepthBuffer===!1&&l){const M=b.stencilBuffer?i.DEPTH_STENCIL_ATTACHMENT:i.DEPTH_ATTACHMENT;i.invalidateFramebuffer(i.DRAW_FRAMEBUFFER,[M])}}}function Ut(b){return Math.min(s.maxSamples,b.samples)}function Gt(b){const M=n.get(b);return b.samples>0&&t.has("WEBGL_multisampled_render_to_texture")===!0&&M.__useRenderToTexture!==!1}function ut(b){const M=a.render.frame;d.get(b)!==M&&(d.set(b,M),b.update())}function At(b,M){const B=b.colorSpace,Y=b.format,Z=b.type;return b.isCompressedTexture===!0||b.isVideoTexture===!0||B!==In&&B!==Cn&&(Jt.getTransfer(B)===se?(Y!==rn||Z!==Mn)&&console.warn("THREE.WebGLTextures: sRGB encoded textures have to use RGBAFormat and UnsignedByteType."):console.error("THREE.WebGLTextures: Unsupported texture color space:",B)),M}function bt(b){return typeof HTMLImageElement<"u"&&b instanceof HTMLImageElement?(h.width=b.naturalWidth||b.width,h.height=b.naturalHeight||b.height):typeof VideoFrame<"u"&&b instanceof VideoFrame?(h.width=b.displayWidth,h.height=b.displayHeight):(h.width=b.width,h.height=b.height),h}this.allocateTextureUnit=z,this.resetTextureUnits=E,this.setTexture2D=K,this.setTexture2DArray=G,this.setTexture3D=I,this.setTextureCube=F,this.rebindTextures=Tt,this.setupRenderTarget=kt,this.updateRenderTargetMipmap=Kt,this.updateMultisampleRenderTarget=ye,this.setupDepthRenderbuffer=mt,this.setupFrameBufferTexture=J,this.useMultisampledRTT=Gt}function Im(i,t){function e(n,s=Cn){let r;const a=Jt.getTransfer(s);if(n===Mn)return i.UNSIGNED_BYTE;if(n===Oa)return i.UNSIGNED_SHORT_4_4_4_4;if(n===Ba)return i.UNSIGNED_SHORT_5_5_5_1;if(n===Fl)return i.UNSIGNED_INT_5_9_9_9_REV;if(n===Ul)return i.BYTE;if(n===Nl)return i.SHORT;if(n===rs)return i.UNSIGNED_SHORT;if(n===Fa)return i.INT;if(n===Zn)return i.UNSIGNED_INT;if(n===cn)return i.FLOAT;if(n===os)return i.HALF_FLOAT;if(n===Ol)return i.ALPHA;if(n===Bl)return i.RGB;if(n===rn)return i.RGBA;if(n===kl)return i.LUMINANCE;if(n===zl)return i.LUMINANCE_ALPHA;if(n===bi)return i.DEPTH_COMPONENT;if(n===Di)return i.DEPTH_STENCIL;if(n===ka)return i.RED;if(n===za)return i.RED_INTEGER;if(n===Hl)return i.RG;if(n===Ha)return i.RG_INTEGER;if(n===Ga)return i.RGBA_INTEGER;if(n===zs||n===Hs||n===Gs||n===Vs)if(a===se)if(r=t.get("WEBGL_compressed_texture_s3tc_srgb"),r!==null){if(n===zs)return r.COMPRESSED_SRGB_S3TC_DXT1_EXT;if(n===Hs)return r.COMPRESSED_SRGB_ALPHA_S3TC_DXT1_EXT;if(n===Gs)return r.COMPRESSED_SRGB_ALPHA_S3TC_DXT3_EXT;if(n===Vs)return r.COMPRESSED_SRGB_ALPHA_S3TC_DXT5_EXT}else return null;else if(r=t.get("WEBGL_compressed_texture_s3tc"),r!==null){if(n===zs)return r.COMPRESSED_RGB_S3TC_DXT1_EXT;if(n===Hs)return r.COMPRESSED_RGBA_S3TC_DXT1_EXT;if(n===Gs)return r.COMPRESSED_RGBA_S3TC_DXT3_EXT;if(n===Vs)return r.COMPRESSED_RGBA_S3TC_DXT5_EXT}else return null;if(n===ra||n===aa||n===oa||n===la)if(r=t.get("WEBGL_compressed_texture_pvrtc"),r!==null){if(n===ra)return r.COMPRESSED_RGB_PVRTC_4BPPV1_IMG;if(n===aa)return r.COMPRESSED_RGB_PVRTC_2BPPV1_IMG;if(n===oa)return r.COMPRESSED_RGBA_PVRTC_4BPPV1_IMG;if(n===la)return r.COMPRESSED_RGBA_PVRTC_2BPPV1_IMG}else return null;if(n===ca||n===ha||n===ua)if(r=t.get("WEBGL_compressed_texture_etc"),r!==null){if(n===ca||n===ha)return a===se?r.COMPRESSED_SRGB8_ETC2:r.COMPRESSED_RGB8_ETC2;if(n===ua)return a===se?r.COMPRESSED_SRGB8_ALPHA8_ETC2_EAC:r.COMPRESSED_RGBA8_ETC2_EAC}else return null;if(n===da||n===fa||n===pa||n===ma||n===ga||n===_a||n===xa||n===va||n===Ma||n===ya||n===Sa||n===wa||n===Ea||n===ba)if(r=t.get("WEBGL_compressed_texture_astc"),r!==null){if(n===da)return a===se?r.COMPRESSED_SRGB8_ALPHA8_ASTC_4x4_KHR:r.COMPRESSED_RGBA_ASTC_4x4_KHR;if(n===fa)return a===se?r.COMPRESSED_SRGB8_ALPHA8_ASTC_5x4_KHR:r.COMPRESSED_RGBA_ASTC_5x4_KHR;if(n===pa)return a===se?r.COMPRESSED_SRGB8_ALPHA8_ASTC_5x5_KHR:r.COMPRESSED_RGBA_ASTC_5x5_KHR;if(n===ma)return a===se?r.COMPRESSED_SRGB8_ALPHA8_ASTC_6x5_KHR:r.COMPRESSED_RGBA_ASTC_6x5_KHR;if(n===ga)return a===se?r.COMPRESSED_SRGB8_ALPHA8_ASTC_6x6_KHR:r.COMPRESSED_RGBA_ASTC_6x6_KHR;if(n===_a)return a===se?r.COMPRESSED_SRGB8_ALPHA8_ASTC_8x5_KHR:r.COMPRESSED_RGBA_ASTC_8x5_KHR;if(n===xa)return a===se?r.COMPRESSED_SRGB8_ALPHA8_ASTC_8x6_KHR:r.COMPRESSED_RGBA_ASTC_8x6_KHR;if(n===va)return a===se?r.COMPRESSED_SRGB8_ALPHA8_ASTC_8x8_KHR:r.COMPRESSED_RGBA_ASTC_8x8_KHR;if(n===Ma)return a===se?r.COMPRESSED_SRGB8_ALPHA8_ASTC_10x5_KHR:r.COMPRESSED_RGBA_ASTC_10x5_KHR;if(n===ya)return a===se?r.COMPRESSED_SRGB8_ALPHA8_ASTC_10x6_KHR:r.COMPRESSED_RGBA_ASTC_10x6_KHR;if(n===Sa)return a===se?r.COMPRESSED_SRGB8_ALPHA8_ASTC_10x8_KHR:r.COMPRESSED_RGBA_ASTC_10x8_KHR;if(n===wa)return a===se?r.COMPRESSED_SRGB8_ALPHA8_ASTC_10x10_KHR:r.COMPRESSED_RGBA_ASTC_10x10_KHR;if(n===Ea)return a===se?r.COMPRESSED_SRGB8_ALPHA8_ASTC_12x10_KHR:r.COMPRESSED_RGBA_ASTC_12x10_KHR;if(n===ba)return a===se?r.COMPRESSED_SRGB8_ALPHA8_ASTC_12x12_KHR:r.COMPRESSED_RGBA_ASTC_12x12_KHR}else return null;if(n===Ws||n===Ta||n===Aa)if(r=t.get("EXT_texture_compression_bptc"),r!==null){if(n===Ws)return a===se?r.COMPRESSED_SRGB_ALPHA_BPTC_UNORM_EXT:r.COMPRESSED_RGBA_BPTC_UNORM_EXT;if(n===Ta)return r.COMPRESSED_RGB_BPTC_SIGNED_FLOAT_EXT;if(n===Aa)return r.COMPRESSED_RGB_BPTC_UNSIGNED_FLOAT_EXT}else return null;if(n===Gl||n===Ra||n===Ca||n===Pa)if(r=t.get("EXT_texture_compression_rgtc"),r!==null){if(n===Ws)return r.COMPRESSED_RED_RGTC1_EXT;if(n===Ra)return r.COMPRESSED_SIGNED_RED_RGTC1_EXT;if(n===Ca)return r.COMPRESSED_RED_GREEN_RGTC2_EXT;if(n===Pa)return r.COMPRESSED_SIGNED_RED_GREEN_RGTC2_EXT}else return null;return n===Li?i.UNSIGNED_INT_24_8:i[n]!==void 0?i[n]:null}return{convert:e}}class Um extends Ve{constructor(t=[]){super(),this.isArrayCamera=!0,this.cameras=t}}class Ze extends me{constructor(){super(),this.isGroup=!0,this.type="Group"}}const Nm={type:"move"};class zr{constructor(){this._targetRay=null,this._grip=null,this._hand=null}getHandSpace(){return this._hand===null&&(this._hand=new Ze,this._hand.matrixAutoUpdate=!1,this._hand.visible=!1,this._hand.joints={},this._hand.inputState={pinching:!1}),this._hand}getTargetRaySpace(){return this._targetRay===null&&(this._targetRay=new Ze,this._targetRay.matrixAutoUpdate=!1,this._targetRay.visible=!1,this._targetRay.hasLinearVelocity=!1,this._targetRay.linearVelocity=new R,this._targetRay.hasAngularVelocity=!1,this._targetRay.angularVelocity=new R),this._targetRay}getGripSpace(){return this._grip===null&&(this._grip=new Ze,this._grip.matrixAutoUpdate=!1,this._grip.visible=!1,this._grip.hasLinearVelocity=!1,this._grip.linearVelocity=new R,this._grip.hasAngularVelocity=!1,this._grip.angularVelocity=new R),this._grip}dispatchEvent(t){return this._targetRay!==null&&this._targetRay.dispatchEvent(t),this._grip!==null&&this._grip.dispatchEvent(t),this._hand!==null&&this._hand.dispatchEvent(t),this}connect(t){if(t&&t.hand){const e=this._hand;if(e)for(const n of t.hand.values())this._getHandJoint(e,n)}return this.dispatchEvent({type:"connected",data:t}),this}disconnect(t){return this.dispatchEvent({type:"disconnected",data:t}),this._targetRay!==null&&(this._targetRay.visible=!1),this._grip!==null&&(this._grip.visible=!1),this._hand!==null&&(this._hand.visible=!1),this}update(t,e,n){let s=null,r=null,a=null;const o=this._targetRay,l=this._grip,h=this._hand;if(t&&e.session.visibilityState!=="visible-blurred"){if(h&&t.hand){a=!0;for(const v of t.hand.values()){const m=e.getJointPose(v,n),p=this._getHandJoint(h,v);m!==null&&(p.matrix.fromArray(m.transform.matrix),p.matrix.decompose(p.position,p.rotation,p.scale),p.matrixWorldNeedsUpdate=!0,p.jointRadius=m.radius),p.visible=m!==null}const d=h.joints["index-finger-tip"],c=h.joints["thumb-tip"],u=d.position.distanceTo(c.position),f=.02,g=.005;h.inputState.pinching&&u>f+g?(h.inputState.pinching=!1,this.dispatchEvent({type:"pinchend",handedness:t.handedness,target:this})):!h.inputState.pinching&&u<=f-g&&(h.inputState.pinching=!0,this.dispatchEvent({type:"pinchstart",handedness:t.handedness,target:this}))}else l!==null&&t.gripSpace&&(r=e.getPose(t.gripSpace,n),r!==null&&(l.matrix.fromArray(r.transform.matrix),l.matrix.decompose(l.position,l.rotation,l.scale),l.matrixWorldNeedsUpdate=!0,r.linearVelocity?(l.hasLinearVelocity=!0,l.linearVelocity.copy(r.linearVelocity)):l.hasLinearVelocity=!1,r.angularVelocity?(l.hasAngularVelocity=!0,l.angularVelocity.copy(r.angularVelocity)):l.hasAngularVelocity=!1));o!==null&&(s=e.getPose(t.targetRaySpace,n),s===null&&r!==null&&(s=r),s!==null&&(o.matrix.fromArray(s.transform.matrix),o.matrix.decompose(o.position,o.rotation,o.scale),o.matrixWorldNeedsUpdate=!0,s.linearVelocity?(o.hasLinearVelocity=!0,o.linearVelocity.copy(s.linearVelocity)):o.hasLinearVelocity=!1,s.angularVelocity?(o.hasAngularVelocity=!0,o.angularVelocity.copy(s.angularVelocity)):o.hasAngularVelocity=!1,this.dispatchEvent(Nm)))}return o!==null&&(o.visible=s!==null),l!==null&&(l.visible=r!==null),h!==null&&(h.visible=a!==null),this}_getHandJoint(t,e){if(t.joints[e.jointName]===void 0){const n=new Ze;n.matrixAutoUpdate=!1,n.visible=!1,t.joints[e.jointName]=n,t.add(n)}return t.joints[e.jointName]}}const Fm=`
void main() {

	gl_Position = vec4( position, 1.0 );

}`,Om=`
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

}`;class Bm{constructor(){this.texture=null,this.mesh=null,this.depthNear=0,this.depthFar=0}init(t,e,n){if(this.texture===null){const s=new be,r=t.properties.get(s);r.__webglTexture=e.texture,(e.depthNear!=n.depthNear||e.depthFar!=n.depthFar)&&(this.depthNear=e.depthNear,this.depthFar=e.depthFar),this.texture=s}}getMesh(t){if(this.texture!==null&&this.mesh===null){const e=t.cameras[0].viewport,n=new an({vertexShader:Fm,fragmentShader:Om,uniforms:{depthColor:{value:this.texture},depthWidth:{value:e.z},depthHeight:{value:e.w}}});this.mesh=new Ct(new Qn(20,20),n)}return this.mesh}reset(){this.texture=null,this.mesh=null}getDepthTexture(){return this.texture}}class km extends Ni{constructor(t,e){super();const n=this;let s=null,r=1,a=null,o="local-floor",l=1,h=null,d=null,c=null,u=null,f=null,g=null;const v=new Bm,m=e.getContextAttributes();let p=null,y=null;const _=[],S=[],P=new Ht;let T=null;const A=new Ve;A.layers.enable(1),A.viewport=new te;const L=new Ve;L.layers.enable(2),L.viewport=new te;const q=[A,L],x=new Um;x.layers.enable(1),x.layers.enable(2);let E=null,z=null;this.cameraAutoUpdate=!0,this.enabled=!1,this.isPresenting=!1,this.getController=function(W){let J=_[W];return J===void 0&&(J=new zr,_[W]=J),J.getTargetRaySpace()},this.getControllerGrip=function(W){let J=_[W];return J===void 0&&(J=new zr,_[W]=J),J.getGripSpace()},this.getHand=function(W){let J=_[W];return J===void 0&&(J=new zr,_[W]=J),J.getHandSpace()};function V(W){const J=S.indexOf(W.inputSource);if(J===-1)return;const it=_[J];it!==void 0&&(it.update(W.inputSource,W.frame,h||a),it.dispatchEvent({type:W.type,data:W.inputSource}))}function K(){s.removeEventListener("select",V),s.removeEventListener("selectstart",V),s.removeEventListener("selectend",V),s.removeEventListener("squeeze",V),s.removeEventListener("squeezestart",V),s.removeEventListener("squeezeend",V),s.removeEventListener("end",K),s.removeEventListener("inputsourceschange",G);for(let W=0;W<_.length;W++){const J=S[W];J!==null&&(S[W]=null,_[W].disconnect(J))}E=null,z=null,v.reset(),t.setRenderTarget(p),f=null,u=null,c=null,s=null,y=null,ot.stop(),n.isPresenting=!1,t.setPixelRatio(T),t.setSize(P.width,P.height,!1),n.dispatchEvent({type:"sessionend"})}this.setFramebufferScaleFactor=function(W){r=W,n.isPresenting===!0&&console.warn("THREE.WebXRManager: Cannot change framebuffer scale while presenting.")},this.setReferenceSpaceType=function(W){o=W,n.isPresenting===!0&&console.warn("THREE.WebXRManager: Cannot change reference space type while presenting.")},this.getReferenceSpace=function(){return h||a},this.setReferenceSpace=function(W){h=W},this.getBaseLayer=function(){return u!==null?u:f},this.getBinding=function(){return c},this.getFrame=function(){return g},this.getSession=function(){return s},this.setSession=async function(W){if(s=W,s!==null){if(p=t.getRenderTarget(),s.addEventListener("select",V),s.addEventListener("selectstart",V),s.addEventListener("selectend",V),s.addEventListener("squeeze",V),s.addEventListener("squeezestart",V),s.addEventListener("squeezeend",V),s.addEventListener("end",K),s.addEventListener("inputsourceschange",G),m.xrCompatible!==!0&&await e.makeXRCompatible(),T=t.getPixelRatio(),t.getSize(P),s.renderState.layers===void 0){const J={antialias:m.antialias,alpha:!0,depth:m.depth,stencil:m.stencil,framebufferScaleFactor:r};f=new XRWebGLLayer(s,e,J),s.updateRenderState({baseLayer:f}),t.setPixelRatio(1),t.setSize(f.framebufferWidth,f.framebufferHeight,!1),y=new $n(f.framebufferWidth,f.framebufferHeight,{format:rn,type:Mn,colorSpace:t.outputColorSpace,stencilBuffer:m.stencil})}else{let J=null,it=null,pt=null;m.depth&&(pt=m.stencil?e.DEPTH24_STENCIL8:e.DEPTH_COMPONENT24,J=m.stencil?Di:bi,it=m.stencil?Li:Zn);const mt={colorFormat:e.RGBA8,depthFormat:pt,scaleFactor:r};c=new XRWebGLBinding(s,e),u=c.createProjectionLayer(mt),s.updateRenderState({layers:[u]}),t.setPixelRatio(1),t.setSize(u.textureWidth,u.textureHeight,!1),y=new $n(u.textureWidth,u.textureHeight,{format:rn,type:Mn,depthTexture:new nc(u.textureWidth,u.textureHeight,it,void 0,void 0,void 0,void 0,void 0,void 0,J),stencilBuffer:m.stencil,colorSpace:t.outputColorSpace,samples:m.antialias?4:0,resolveDepthBuffer:u.ignoreDepthValues===!1})}y.isXRRenderTarget=!0,this.setFoveation(l),h=null,a=await s.requestReferenceSpace(o),ot.setContext(s),ot.start(),n.isPresenting=!0,n.dispatchEvent({type:"sessionstart"})}},this.getEnvironmentBlendMode=function(){if(s!==null)return s.environmentBlendMode},this.getDepthTexture=function(){return v.getDepthTexture()};function G(W){for(let J=0;J<W.removed.length;J++){const it=W.removed[J],pt=S.indexOf(it);pt>=0&&(S[pt]=null,_[pt].disconnect(it))}for(let J=0;J<W.added.length;J++){const it=W.added[J];let pt=S.indexOf(it);if(pt===-1){for(let Tt=0;Tt<_.length;Tt++)if(Tt>=S.length){S.push(it),pt=Tt;break}else if(S[Tt]===null){S[Tt]=it,pt=Tt;break}if(pt===-1)break}const mt=_[pt];mt&&mt.connect(it)}}const I=new R,F=new R;function O(W,J,it){I.setFromMatrixPosition(J.matrixWorld),F.setFromMatrixPosition(it.matrixWorld);const pt=I.distanceTo(F),mt=J.projectionMatrix.elements,Tt=it.projectionMatrix.elements,kt=mt[14]/(mt[10]-1),Kt=mt[14]/(mt[10]+1),Bt=(mt[9]+1)/mt[5],C=(mt[9]-1)/mt[5],ye=(mt[8]-1)/mt[0],Ut=(Tt[8]+1)/Tt[0],Gt=kt*ye,ut=kt*Ut,At=pt/(-ye+Ut),bt=At*-ye;if(J.matrixWorld.decompose(W.position,W.quaternion,W.scale),W.translateX(bt),W.translateZ(At),W.matrixWorld.compose(W.position,W.quaternion,W.scale),W.matrixWorldInverse.copy(W.matrixWorld).invert(),mt[10]===-1)W.projectionMatrix.copy(J.projectionMatrix),W.projectionMatrixInverse.copy(J.projectionMatrixInverse);else{const b=kt+At,M=Kt+At,B=Gt-bt,Y=ut+(pt-bt),Z=Bt*Kt/M*b,j=C*Kt/M*b;W.projectionMatrix.makePerspective(B,Y,Z,j,b,M),W.projectionMatrixInverse.copy(W.projectionMatrix).invert()}}function Q(W,J){J===null?W.matrixWorld.copy(W.matrix):W.matrixWorld.multiplyMatrices(J.matrixWorld,W.matrix),W.matrixWorldInverse.copy(W.matrixWorld).invert()}this.updateCamera=function(W){if(s===null)return;let J=W.near,it=W.far;v.texture!==null&&(v.depthNear>0&&(J=v.depthNear),v.depthFar>0&&(it=v.depthFar)),x.near=L.near=A.near=J,x.far=L.far=A.far=it,(E!==x.near||z!==x.far)&&(s.updateRenderState({depthNear:x.near,depthFar:x.far}),E=x.near,z=x.far);const pt=W.parent,mt=x.cameras;Q(x,pt);for(let Tt=0;Tt<mt.length;Tt++)Q(mt[Tt],pt);mt.length===2?O(x,A,L):x.projectionMatrix.copy(A.projectionMatrix),nt(W,x,pt)};function nt(W,J,it){it===null?W.matrix.copy(J.matrixWorld):(W.matrix.copy(it.matrixWorld),W.matrix.invert(),W.matrix.multiply(J.matrixWorld)),W.matrix.decompose(W.position,W.quaternion,W.scale),W.updateMatrixWorld(!0),W.projectionMatrix.copy(J.projectionMatrix),W.projectionMatrixInverse.copy(J.projectionMatrixInverse),W.isPerspectiveCamera&&(W.fov=as*2*Math.atan(1/W.projectionMatrix.elements[5]),W.zoom=1)}this.getCamera=function(){return x},this.getFoveation=function(){if(!(u===null&&f===null))return l},this.setFoveation=function(W){l=W,u!==null&&(u.fixedFoveation=W),f!==null&&f.fixedFoveation!==void 0&&(f.fixedFoveation=W)},this.hasDepthSensing=function(){return v.texture!==null},this.getDepthSensingMesh=function(){return v.getMesh(x)};let rt=null;function ht(W,J){if(d=J.getViewerPose(h||a),g=J,d!==null){const it=d.views;f!==null&&(t.setRenderTargetFramebuffer(y,f.framebuffer),t.setRenderTarget(y));let pt=!1;it.length!==x.cameras.length&&(x.cameras.length=0,pt=!0);for(let Tt=0;Tt<it.length;Tt++){const kt=it[Tt];let Kt=null;if(f!==null)Kt=f.getViewport(kt);else{const C=c.getViewSubImage(u,kt);Kt=C.viewport,Tt===0&&(t.setRenderTargetTextures(y,C.colorTexture,u.ignoreDepthValues?void 0:C.depthStencilTexture),t.setRenderTarget(y))}let Bt=q[Tt];Bt===void 0&&(Bt=new Ve,Bt.layers.enable(Tt),Bt.viewport=new te,q[Tt]=Bt),Bt.matrix.fromArray(kt.transform.matrix),Bt.matrix.decompose(Bt.position,Bt.quaternion,Bt.scale),Bt.projectionMatrix.fromArray(kt.projectionMatrix),Bt.projectionMatrixInverse.copy(Bt.projectionMatrix).invert(),Bt.viewport.set(Kt.x,Kt.y,Kt.width,Kt.height),Tt===0&&(x.matrix.copy(Bt.matrix),x.matrix.decompose(x.position,x.quaternion,x.scale)),pt===!0&&x.cameras.push(Bt)}const mt=s.enabledFeatures;if(mt&&mt.includes("depth-sensing")){const Tt=c.getDepthInformation(it[0]);Tt&&Tt.isValid&&Tt.texture&&v.init(t,Tt,s.renderState)}}for(let it=0;it<_.length;it++){const pt=S[it],mt=_[it];pt!==null&&mt!==void 0&&mt.update(pt,J,h||a)}rt&&rt(W,J),J.detectedPlanes&&n.dispatchEvent({type:"planesdetected",data:J}),g=null}const ot=new tc;ot.setAnimationLoop(ht),this.setAnimationLoop=function(W){rt=W},this.dispose=function(){}}}const Hn=new on,zm=new ee;function Hm(i,t){function e(m,p){m.matrixAutoUpdate===!0&&m.updateMatrix(),p.value.copy(m.matrix)}function n(m,p){p.color.getRGB(m.fogColor.value,$l(i)),p.isFog?(m.fogNear.value=p.near,m.fogFar.value=p.far):p.isFogExp2&&(m.fogDensity.value=p.density)}function s(m,p,y,_,S){p.isMeshBasicMaterial||p.isMeshLambertMaterial?r(m,p):p.isMeshToonMaterial?(r(m,p),c(m,p)):p.isMeshPhongMaterial?(r(m,p),d(m,p)):p.isMeshStandardMaterial?(r(m,p),u(m,p),p.isMeshPhysicalMaterial&&f(m,p,S)):p.isMeshMatcapMaterial?(r(m,p),g(m,p)):p.isMeshDepthMaterial?r(m,p):p.isMeshDistanceMaterial?(r(m,p),v(m,p)):p.isMeshNormalMaterial?r(m,p):p.isLineBasicMaterial?(a(m,p),p.isLineDashedMaterial&&o(m,p)):p.isPointsMaterial?l(m,p,y,_):p.isSpriteMaterial?h(m,p):p.isShadowMaterial?(m.color.value.copy(p.color),m.opacity.value=p.opacity):p.isShaderMaterial&&(p.uniformsNeedUpdate=!1)}function r(m,p){m.opacity.value=p.opacity,p.color&&m.diffuse.value.copy(p.color),p.emissive&&m.emissive.value.copy(p.emissive).multiplyScalar(p.emissiveIntensity),p.map&&(m.map.value=p.map,e(p.map,m.mapTransform)),p.alphaMap&&(m.alphaMap.value=p.alphaMap,e(p.alphaMap,m.alphaMapTransform)),p.bumpMap&&(m.bumpMap.value=p.bumpMap,e(p.bumpMap,m.bumpMapTransform),m.bumpScale.value=p.bumpScale,p.side===Pe&&(m.bumpScale.value*=-1)),p.normalMap&&(m.normalMap.value=p.normalMap,e(p.normalMap,m.normalMapTransform),m.normalScale.value.copy(p.normalScale),p.side===Pe&&m.normalScale.value.negate()),p.displacementMap&&(m.displacementMap.value=p.displacementMap,e(p.displacementMap,m.displacementMapTransform),m.displacementScale.value=p.displacementScale,m.displacementBias.value=p.displacementBias),p.emissiveMap&&(m.emissiveMap.value=p.emissiveMap,e(p.emissiveMap,m.emissiveMapTransform)),p.specularMap&&(m.specularMap.value=p.specularMap,e(p.specularMap,m.specularMapTransform)),p.alphaTest>0&&(m.alphaTest.value=p.alphaTest);const y=t.get(p),_=y.envMap,S=y.envMapRotation;_&&(m.envMap.value=_,Hn.copy(S),Hn.x*=-1,Hn.y*=-1,Hn.z*=-1,_.isCubeTexture&&_.isRenderTargetTexture===!1&&(Hn.y*=-1,Hn.z*=-1),m.envMapRotation.value.setFromMatrix4(zm.makeRotationFromEuler(Hn)),m.flipEnvMap.value=_.isCubeTexture&&_.isRenderTargetTexture===!1?-1:1,m.reflectivity.value=p.reflectivity,m.ior.value=p.ior,m.refractionRatio.value=p.refractionRatio),p.lightMap&&(m.lightMap.value=p.lightMap,m.lightMapIntensity.value=p.lightMapIntensity,e(p.lightMap,m.lightMapTransform)),p.aoMap&&(m.aoMap.value=p.aoMap,m.aoMapIntensity.value=p.aoMapIntensity,e(p.aoMap,m.aoMapTransform))}function a(m,p){m.diffuse.value.copy(p.color),m.opacity.value=p.opacity,p.map&&(m.map.value=p.map,e(p.map,m.mapTransform))}function o(m,p){m.dashSize.value=p.dashSize,m.totalSize.value=p.dashSize+p.gapSize,m.scale.value=p.scale}function l(m,p,y,_){m.diffuse.value.copy(p.color),m.opacity.value=p.opacity,m.size.value=p.size*y,m.scale.value=_*.5,p.map&&(m.map.value=p.map,e(p.map,m.uvTransform)),p.alphaMap&&(m.alphaMap.value=p.alphaMap,e(p.alphaMap,m.alphaMapTransform)),p.alphaTest>0&&(m.alphaTest.value=p.alphaTest)}function h(m,p){m.diffuse.value.copy(p.color),m.opacity.value=p.opacity,m.rotation.value=p.rotation,p.map&&(m.map.value=p.map,e(p.map,m.mapTransform)),p.alphaMap&&(m.alphaMap.value=p.alphaMap,e(p.alphaMap,m.alphaMapTransform)),p.alphaTest>0&&(m.alphaTest.value=p.alphaTest)}function d(m,p){m.specular.value.copy(p.specular),m.shininess.value=Math.max(p.shininess,1e-4)}function c(m,p){p.gradientMap&&(m.gradientMap.value=p.gradientMap)}function u(m,p){m.metalness.value=p.metalness,p.metalnessMap&&(m.metalnessMap.value=p.metalnessMap,e(p.metalnessMap,m.metalnessMapTransform)),m.roughness.value=p.roughness,p.roughnessMap&&(m.roughnessMap.value=p.roughnessMap,e(p.roughnessMap,m.roughnessMapTransform)),p.envMap&&(m.envMapIntensity.value=p.envMapIntensity)}function f(m,p,y){m.ior.value=p.ior,p.sheen>0&&(m.sheenColor.value.copy(p.sheenColor).multiplyScalar(p.sheen),m.sheenRoughness.value=p.sheenRoughness,p.sheenColorMap&&(m.sheenColorMap.value=p.sheenColorMap,e(p.sheenColorMap,m.sheenColorMapTransform)),p.sheenRoughnessMap&&(m.sheenRoughnessMap.value=p.sheenRoughnessMap,e(p.sheenRoughnessMap,m.sheenRoughnessMapTransform))),p.clearcoat>0&&(m.clearcoat.value=p.clearcoat,m.clearcoatRoughness.value=p.clearcoatRoughness,p.clearcoatMap&&(m.clearcoatMap.value=p.clearcoatMap,e(p.clearcoatMap,m.clearcoatMapTransform)),p.clearcoatRoughnessMap&&(m.clearcoatRoughnessMap.value=p.clearcoatRoughnessMap,e(p.clearcoatRoughnessMap,m.clearcoatRoughnessMapTransform)),p.clearcoatNormalMap&&(m.clearcoatNormalMap.value=p.clearcoatNormalMap,e(p.clearcoatNormalMap,m.clearcoatNormalMapTransform),m.clearcoatNormalScale.value.copy(p.clearcoatNormalScale),p.side===Pe&&m.clearcoatNormalScale.value.negate())),p.dispersion>0&&(m.dispersion.value=p.dispersion),p.iridescence>0&&(m.iridescence.value=p.iridescence,m.iridescenceIOR.value=p.iridescenceIOR,m.iridescenceThicknessMinimum.value=p.iridescenceThicknessRange[0],m.iridescenceThicknessMaximum.value=p.iridescenceThicknessRange[1],p.iridescenceMap&&(m.iridescenceMap.value=p.iridescenceMap,e(p.iridescenceMap,m.iridescenceMapTransform)),p.iridescenceThicknessMap&&(m.iridescenceThicknessMap.value=p.iridescenceThicknessMap,e(p.iridescenceThicknessMap,m.iridescenceThicknessMapTransform))),p.transmission>0&&(m.transmission.value=p.transmission,m.transmissionSamplerMap.value=y.texture,m.transmissionSamplerSize.value.set(y.width,y.height),p.transmissionMap&&(m.transmissionMap.value=p.transmissionMap,e(p.transmissionMap,m.transmissionMapTransform)),m.thickness.value=p.thickness,p.thicknessMap&&(m.thicknessMap.value=p.thicknessMap,e(p.thicknessMap,m.thicknessMapTransform)),m.attenuationDistance.value=p.attenuationDistance,m.attenuationColor.value.copy(p.attenuationColor)),p.anisotropy>0&&(m.anisotropyVector.value.set(p.anisotropy*Math.cos(p.anisotropyRotation),p.anisotropy*Math.sin(p.anisotropyRotation)),p.anisotropyMap&&(m.anisotropyMap.value=p.anisotropyMap,e(p.anisotropyMap,m.anisotropyMapTransform))),m.specularIntensity.value=p.specularIntensity,m.specularColor.value.copy(p.specularColor),p.specularColorMap&&(m.specularColorMap.value=p.specularColorMap,e(p.specularColorMap,m.specularColorMapTransform)),p.specularIntensityMap&&(m.specularIntensityMap.value=p.specularIntensityMap,e(p.specularIntensityMap,m.specularIntensityMapTransform))}function g(m,p){p.matcap&&(m.matcap.value=p.matcap)}function v(m,p){const y=t.get(p).light;m.referencePosition.value.setFromMatrixPosition(y.matrixWorld),m.nearDistance.value=y.shadow.camera.near,m.farDistance.value=y.shadow.camera.far}return{refreshFogUniforms:n,refreshMaterialUniforms:s}}function Gm(i,t,e,n){let s={},r={},a=[];const o=i.getParameter(i.MAX_UNIFORM_BUFFER_BINDINGS);function l(y,_){const S=_.program;n.uniformBlockBinding(y,S)}function h(y,_){let S=s[y.id];S===void 0&&(g(y),S=d(y),s[y.id]=S,y.addEventListener("dispose",m));const P=_.program;n.updateUBOMapping(y,P);const T=t.render.frame;r[y.id]!==T&&(u(y),r[y.id]=T)}function d(y){const _=c();y.__bindingPointIndex=_;const S=i.createBuffer(),P=y.__size,T=y.usage;return i.bindBuffer(i.UNIFORM_BUFFER,S),i.bufferData(i.UNIFORM_BUFFER,P,T),i.bindBuffer(i.UNIFORM_BUFFER,null),i.bindBufferBase(i.UNIFORM_BUFFER,_,S),S}function c(){for(let y=0;y<o;y++)if(a.indexOf(y)===-1)return a.push(y),y;return console.error("THREE.WebGLRenderer: Maximum number of simultaneously usable uniforms groups reached."),0}function u(y){const _=s[y.id],S=y.uniforms,P=y.__cache;i.bindBuffer(i.UNIFORM_BUFFER,_);for(let T=0,A=S.length;T<A;T++){const L=Array.isArray(S[T])?S[T]:[S[T]];for(let q=0,x=L.length;q<x;q++){const E=L[q];if(f(E,T,q,P)===!0){const z=E.__offset,V=Array.isArray(E.value)?E.value:[E.value];let K=0;for(let G=0;G<V.length;G++){const I=V[G],F=v(I);typeof I=="number"||typeof I=="boolean"?(E.__data[0]=I,i.bufferSubData(i.UNIFORM_BUFFER,z+K,E.__data)):I.isMatrix3?(E.__data[0]=I.elements[0],E.__data[1]=I.elements[1],E.__data[2]=I.elements[2],E.__data[3]=0,E.__data[4]=I.elements[3],E.__data[5]=I.elements[4],E.__data[6]=I.elements[5],E.__data[7]=0,E.__data[8]=I.elements[6],E.__data[9]=I.elements[7],E.__data[10]=I.elements[8],E.__data[11]=0):(I.toArray(E.__data,K),K+=F.storage/Float32Array.BYTES_PER_ELEMENT)}i.bufferSubData(i.UNIFORM_BUFFER,z,E.__data)}}}i.bindBuffer(i.UNIFORM_BUFFER,null)}function f(y,_,S,P){const T=y.value,A=_+"_"+S;if(P[A]===void 0)return typeof T=="number"||typeof T=="boolean"?P[A]=T:P[A]=T.clone(),!0;{const L=P[A];if(typeof T=="number"||typeof T=="boolean"){if(L!==T)return P[A]=T,!0}else if(L.equals(T)===!1)return L.copy(T),!0}return!1}function g(y){const _=y.uniforms;let S=0;const P=16;for(let A=0,L=_.length;A<L;A++){const q=Array.isArray(_[A])?_[A]:[_[A]];for(let x=0,E=q.length;x<E;x++){const z=q[x],V=Array.isArray(z.value)?z.value:[z.value];for(let K=0,G=V.length;K<G;K++){const I=V[K],F=v(I),O=S%P,Q=O%F.boundary,nt=O+Q;S+=Q,nt!==0&&P-nt<F.storage&&(S+=P-nt),z.__data=new Float32Array(F.storage/Float32Array.BYTES_PER_ELEMENT),z.__offset=S,S+=F.storage}}}const T=S%P;return T>0&&(S+=P-T),y.__size=S,y.__cache={},this}function v(y){const _={boundary:0,storage:0};return typeof y=="number"||typeof y=="boolean"?(_.boundary=4,_.storage=4):y.isVector2?(_.boundary=8,_.storage=8):y.isVector3||y.isColor?(_.boundary=16,_.storage=12):y.isVector4?(_.boundary=16,_.storage=16):y.isMatrix3?(_.boundary=48,_.storage=48):y.isMatrix4?(_.boundary=64,_.storage=64):y.isTexture?console.warn("THREE.WebGLRenderer: Texture samplers can not be part of an uniforms group."):console.warn("THREE.WebGLRenderer: Unsupported uniform value type.",y),_}function m(y){const _=y.target;_.removeEventListener("dispose",m);const S=a.indexOf(_.__bindingPointIndex);a.splice(S,1),i.deleteBuffer(s[_.id]),delete s[_.id],delete r[_.id]}function p(){for(const y in s)i.deleteBuffer(s[y]);a=[],s={},r={}}return{bind:l,update:h,dispose:p}}class Vm{constructor(t={}){const{canvas:e=Ch(),context:n=null,depth:s=!0,stencil:r=!1,alpha:a=!1,antialias:o=!1,premultipliedAlpha:l=!0,preserveDrawingBuffer:h=!1,powerPreference:d="default",failIfMajorPerformanceCaveat:c=!1}=t;this.isWebGLRenderer=!0;let u;if(n!==null){if(typeof WebGLRenderingContext<"u"&&n instanceof WebGLRenderingContext)throw new Error("THREE.WebGLRenderer: WebGL 1 is not supported since r163.");u=n.getContextAttributes().alpha}else u=a;const f=new Uint32Array(4),g=new Int32Array(4);let v=null,m=null;const p=[],y=[];this.domElement=e,this.debug={checkShaderErrors:!0,onShaderError:null},this.autoClear=!0,this.autoClearColor=!0,this.autoClearDepth=!0,this.autoClearStencil=!0,this.sortObjects=!0,this.clippingPlanes=[],this.localClippingEnabled=!1,this._outputColorSpace=je,this.toneMapping=Dn,this.toneMappingExposure=1;const _=this;let S=!1,P=0,T=0,A=null,L=-1,q=null;const x=new te,E=new te;let z=null;const V=new Pt(0);let K=0,G=e.width,I=e.height,F=1,O=null,Q=null;const nt=new te(0,0,G,I),rt=new te(0,0,G,I);let ht=!1;const ot=new qa;let W=!1,J=!1;const it=new ee,pt=new ee,mt=new R,Tt=new te,kt={background:null,fog:null,environment:null,overrideMaterial:null,isScene:!0};let Kt=!1;function Bt(){return A===null?F:1}let C=n;function ye(w,U){return e.getContext(w,U)}try{const w={alpha:!0,depth:s,stencil:r,antialias:o,premultipliedAlpha:l,preserveDrawingBuffer:h,powerPreference:d,failIfMajorPerformanceCaveat:c};if("setAttribute"in e&&e.setAttribute("data-engine",`three.js r${Na}`),e.addEventListener("webglcontextlost",$,!1),e.addEventListener("webglcontextrestored",lt,!1),e.addEventListener("webglcontextcreationerror",ft,!1),C===null){const U="webgl2";if(C=ye(U,w),C===null)throw ye(U)?new Error("Error creating WebGL context with your selected attributes."):new Error("Error creating WebGL context.")}}catch(w){throw console.error("THREE.WebGLRenderer: "+w.message),w}let Ut,Gt,ut,At,bt,b,M,B,Y,Z,j,St,at,gt,qt,tt,_t,Dt,It,xt,Vt,Nt,ne,D;function dt(){Ut=new Kf(C),Ut.init(),Nt=new Im(C,Ut),Gt=new Gf(C,Ut,t,Nt),ut=new Pm(C),Gt.reverseDepthBuffer&&ut.buffers.depth.setReversed(!0),At=new $f(C),bt=new mm,b=new Dm(C,Ut,ut,bt,Gt,Nt,At),M=new Wf(_),B=new qf(_),Y=new iu(C),ne=new zf(C,Y),Z=new jf(C,Y,At,ne),j=new Qf(C,Z,Y,At),It=new Jf(C,Gt,b),tt=new Vf(bt),St=new pm(_,M,B,Ut,Gt,ne,tt),at=new Hm(_,bt),gt=new _m,qt=new wm(Ut),Dt=new kf(_,M,B,ut,j,u,l),_t=new Rm(_,j,Gt),D=new Gm(C,At,Gt,ut),xt=new Hf(C,Ut,At),Vt=new Zf(C,Ut,At),At.programs=St.programs,_.capabilities=Gt,_.extensions=Ut,_.properties=bt,_.renderLists=gt,_.shadowMap=_t,_.state=ut,_.info=At}dt();const X=new km(_,C);this.xr=X,this.getContext=function(){return C},this.getContextAttributes=function(){return C.getContextAttributes()},this.forceContextLoss=function(){const w=Ut.get("WEBGL_lose_context");w&&w.loseContext()},this.forceContextRestore=function(){const w=Ut.get("WEBGL_lose_context");w&&w.restoreContext()},this.getPixelRatio=function(){return F},this.setPixelRatio=function(w){w!==void 0&&(F=w,this.setSize(G,I,!1))},this.getSize=function(w){return w.set(G,I)},this.setSize=function(w,U,k=!0){if(X.isPresenting){console.warn("THREE.WebGLRenderer: Can't change size while VR device is presenting.");return}G=w,I=U,e.width=Math.floor(w*F),e.height=Math.floor(U*F),k===!0&&(e.style.width=w+"px",e.style.height=U+"px"),this.setViewport(0,0,w,U)},this.getDrawingBufferSize=function(w){return w.set(G*F,I*F).floor()},this.setDrawingBufferSize=function(w,U,k){G=w,I=U,F=k,e.width=Math.floor(w*k),e.height=Math.floor(U*k),this.setViewport(0,0,w,U)},this.getCurrentViewport=function(w){return w.copy(x)},this.getViewport=function(w){return w.copy(nt)},this.setViewport=function(w,U,k,H){w.isVector4?nt.set(w.x,w.y,w.z,w.w):nt.set(w,U,k,H),ut.viewport(x.copy(nt).multiplyScalar(F).round())},this.getScissor=function(w){return w.copy(rt)},this.setScissor=function(w,U,k,H){w.isVector4?rt.set(w.x,w.y,w.z,w.w):rt.set(w,U,k,H),ut.scissor(E.copy(rt).multiplyScalar(F).round())},this.getScissorTest=function(){return ht},this.setScissorTest=function(w){ut.setScissorTest(ht=w)},this.setOpaqueSort=function(w){O=w},this.setTransparentSort=function(w){Q=w},this.getClearColor=function(w){return w.copy(Dt.getClearColor())},this.setClearColor=function(){Dt.setClearColor.apply(Dt,arguments)},this.getClearAlpha=function(){return Dt.getClearAlpha()},this.setClearAlpha=function(){Dt.setClearAlpha.apply(Dt,arguments)},this.clear=function(w=!0,U=!0,k=!0){let H=0;if(w){let N=!1;if(A!==null){const et=A.texture.format;N=et===Ga||et===Ha||et===za}if(N){const et=A.texture.type,ct=et===Mn||et===Zn||et===rs||et===Li||et===Oa||et===Ba,vt=Dt.getClearColor(),yt=Dt.getClearAlpha(),Rt=vt.r,Lt=vt.g,wt=vt.b;ct?(f[0]=Rt,f[1]=Lt,f[2]=wt,f[3]=yt,C.clearBufferuiv(C.COLOR,0,f)):(g[0]=Rt,g[1]=Lt,g[2]=wt,g[3]=yt,C.clearBufferiv(C.COLOR,0,g))}else H|=C.COLOR_BUFFER_BIT}U&&(H|=C.DEPTH_BUFFER_BIT,C.clearDepth(this.capabilities.reverseDepthBuffer?0:1)),k&&(H|=C.STENCIL_BUFFER_BIT,this.state.buffers.stencil.setMask(4294967295)),C.clear(H)},this.clearColor=function(){this.clear(!0,!1,!1)},this.clearDepth=function(){this.clear(!1,!0,!1)},this.clearStencil=function(){this.clear(!1,!1,!0)},this.dispose=function(){e.removeEventListener("webglcontextlost",$,!1),e.removeEventListener("webglcontextrestored",lt,!1),e.removeEventListener("webglcontextcreationerror",ft,!1),gt.dispose(),qt.dispose(),bt.dispose(),M.dispose(),B.dispose(),j.dispose(),ne.dispose(),D.dispose(),St.dispose(),X.dispose(),X.removeEventListener("sessionstart",Ja),X.removeEventListener("sessionend",Qa),Nn.stop()};function $(w){w.preventDefault(),console.log("THREE.WebGLRenderer: Context Lost."),S=!0}function lt(){console.log("THREE.WebGLRenderer: Context Restored."),S=!1;const w=At.autoReset,U=_t.enabled,k=_t.autoUpdate,H=_t.needsUpdate,N=_t.type;dt(),At.autoReset=w,_t.enabled=U,_t.autoUpdate=k,_t.needsUpdate=H,_t.type=N}function ft(w){console.error("THREE.WebGLRenderer: A WebGL context could not be created. Reason: ",w.statusMessage)}function Xt(w){const U=w.target;U.removeEventListener("dispose",Xt),he(U)}function he(w){De(w),bt.remove(w)}function De(w){const U=bt.get(w).programs;U!==void 0&&(U.forEach(function(k){St.releaseProgram(k)}),w.isShaderMaterial&&St.releaseShaderCache(w))}this.renderBufferDirect=function(w,U,k,H,N,et){U===null&&(U=kt);const ct=N.isMesh&&N.matrixWorld.determinant()<0,vt=gc(w,U,k,H,N);ut.setMaterial(H,ct);let yt=k.index,Rt=1;if(H.wireframe===!0){if(yt=Z.getWireframeAttribute(k),yt===void 0)return;Rt=2}const Lt=k.drawRange,wt=k.attributes.position;let Qt=Lt.start*Rt,ie=(Lt.start+Lt.count)*Rt;et!==null&&(Qt=Math.max(Qt,et.start*Rt),ie=Math.min(ie,(et.start+et.count)*Rt)),yt!==null?(Qt=Math.max(Qt,0),ie=Math.min(ie,yt.count)):wt!=null&&(Qt=Math.max(Qt,0),ie=Math.min(ie,wt.count));const ae=ie-Qt;if(ae<0||ae===1/0)return;ne.setup(N,H,vt,k,yt);let Ne,Zt=xt;if(yt!==null&&(Ne=Y.get(yt),Zt=Vt,Zt.setIndex(Ne)),N.isMesh)H.wireframe===!0?(ut.setLineWidth(H.wireframeLinewidth*Bt()),Zt.setMode(C.LINES)):Zt.setMode(C.TRIANGLES);else if(N.isLine){let Et=H.linewidth;Et===void 0&&(Et=1),ut.setLineWidth(Et*Bt()),N.isLineSegments?Zt.setMode(C.LINES):N.isLineLoop?Zt.setMode(C.LINE_LOOP):Zt.setMode(C.LINE_STRIP)}else N.isPoints?Zt.setMode(C.POINTS):N.isSprite&&Zt.setMode(C.TRIANGLES);if(N.isBatchedMesh)if(N._multiDrawInstances!==null)Zt.renderMultiDrawInstances(N._multiDrawStarts,N._multiDrawCounts,N._multiDrawCount,N._multiDrawInstances);else if(Ut.get("WEBGL_multi_draw"))Zt.renderMultiDraw(N._multiDrawStarts,N._multiDrawCounts,N._multiDrawCount);else{const Et=N._multiDrawStarts,ve=N._multiDrawCounts,$t=N._multiDrawCount,$e=yt?Y.get(yt).bytesPerElement:1,ei=bt.get(H).currentProgram.getUniforms();for(let Fe=0;Fe<$t;Fe++)ei.setValue(C,"_gl_DrawID",Fe),Zt.render(Et[Fe]/$e,ve[Fe])}else if(N.isInstancedMesh)Zt.renderInstances(Qt,ae,N.count);else if(k.isInstancedBufferGeometry){const Et=k._maxInstanceCount!==void 0?k._maxInstanceCount:1/0,ve=Math.min(k.instanceCount,Et);Zt.renderInstances(Qt,ae,ve)}else Zt.render(Qt,ae)};function jt(w,U,k){w.transparent===!0&&w.side===de&&w.forceSinglePass===!1?(w.side=Pe,w.needsUpdate=!0,us(w,U,k),w.side=hn,w.needsUpdate=!0,us(w,U,k),w.side=de):us(w,U,k)}this.compile=function(w,U,k=null){k===null&&(k=w),m=qt.get(k),m.init(U),y.push(m),k.traverseVisible(function(N){N.isLight&&N.layers.test(U.layers)&&(m.pushLight(N),N.castShadow&&m.pushShadow(N))}),w!==k&&w.traverseVisible(function(N){N.isLight&&N.layers.test(U.layers)&&(m.pushLight(N),N.castShadow&&m.pushShadow(N))}),m.setupLights();const H=new Set;return w.traverse(function(N){if(!(N.isMesh||N.isPoints||N.isLine||N.isSprite))return;const et=N.material;if(et)if(Array.isArray(et))for(let ct=0;ct<et.length;ct++){const vt=et[ct];jt(vt,k,N),H.add(vt)}else jt(et,k,N),H.add(et)}),y.pop(),m=null,H},this.compileAsync=function(w,U,k=null){const H=this.compile(w,U,k);return new Promise(N=>{function et(){if(H.forEach(function(ct){bt.get(ct).currentProgram.isReady()&&H.delete(ct)}),H.size===0){N(w);return}setTimeout(et,10)}Ut.get("KHR_parallel_shader_compile")!==null?et():setTimeout(et,10)})};let Ie=null;function un(w){Ie&&Ie(w)}function Ja(){Nn.stop()}function Qa(){Nn.start()}const Nn=new tc;Nn.setAnimationLoop(un),typeof self<"u"&&Nn.setContext(self),this.setAnimationLoop=function(w){Ie=w,X.setAnimationLoop(w),w===null?Nn.stop():Nn.start()},X.addEventListener("sessionstart",Ja),X.addEventListener("sessionend",Qa),this.render=function(w,U){if(U!==void 0&&U.isCamera!==!0){console.error("THREE.WebGLRenderer.render: camera is not an instance of THREE.Camera.");return}if(S===!0)return;if(w.matrixWorldAutoUpdate===!0&&w.updateMatrixWorld(),U.parent===null&&U.matrixWorldAutoUpdate===!0&&U.updateMatrixWorld(),X.enabled===!0&&X.isPresenting===!0&&(X.cameraAutoUpdate===!0&&X.updateCamera(U),U=X.getCamera()),w.isScene===!0&&w.onBeforeRender(_,w,U,A),m=qt.get(w,y.length),m.init(U),y.push(m),pt.multiplyMatrices(U.projectionMatrix,U.matrixWorldInverse),ot.setFromProjectionMatrix(pt),J=this.localClippingEnabled,W=tt.init(this.clippingPlanes,J),v=gt.get(w,p.length),v.init(),p.push(v),X.enabled===!0&&X.isPresenting===!0){const et=_.xr.getDepthSensingMesh();et!==null&&ar(et,U,-1/0,_.sortObjects)}ar(w,U,0,_.sortObjects),v.finish(),_.sortObjects===!0&&v.sort(O,Q),Kt=X.enabled===!1||X.isPresenting===!1||X.hasDepthSensing()===!1,Kt&&Dt.addToRenderList(v,w),this.info.render.frame++,W===!0&&tt.beginShadows();const k=m.state.shadowsArray;_t.render(k,w,U),W===!0&&tt.endShadows(),this.info.autoReset===!0&&this.info.reset();const H=v.opaque,N=v.transmissive;if(m.setupLights(),U.isArrayCamera){const et=U.cameras;if(N.length>0)for(let ct=0,vt=et.length;ct<vt;ct++){const yt=et[ct];eo(H,N,w,yt)}Kt&&Dt.render(w);for(let ct=0,vt=et.length;ct<vt;ct++){const yt=et[ct];to(v,w,yt,yt.viewport)}}else N.length>0&&eo(H,N,w,U),Kt&&Dt.render(w),to(v,w,U);A!==null&&(b.updateMultisampleRenderTarget(A),b.updateRenderTargetMipmap(A)),w.isScene===!0&&w.onAfterRender(_,w,U),ne.resetDefaultState(),L=-1,q=null,y.pop(),y.length>0?(m=y[y.length-1],W===!0&&tt.setGlobalState(_.clippingPlanes,m.state.camera)):m=null,p.pop(),p.length>0?v=p[p.length-1]:v=null};function ar(w,U,k,H){if(w.visible===!1)return;if(w.layers.test(U.layers)){if(w.isGroup)k=w.renderOrder;else if(w.isLOD)w.autoUpdate===!0&&w.update(U);else if(w.isLight)m.pushLight(w),w.castShadow&&m.pushShadow(w);else if(w.isSprite){if(!w.frustumCulled||ot.intersectsSprite(w)){H&&Tt.setFromMatrixPosition(w.matrixWorld).applyMatrix4(pt);const ct=j.update(w),vt=w.material;vt.visible&&v.push(w,ct,vt,k,Tt.z,null)}}else if((w.isMesh||w.isLine||w.isPoints)&&(!w.frustumCulled||ot.intersectsObject(w))){const ct=j.update(w),vt=w.material;if(H&&(w.boundingSphere!==void 0?(w.boundingSphere===null&&w.computeBoundingSphere(),Tt.copy(w.boundingSphere.center)):(ct.boundingSphere===null&&ct.computeBoundingSphere(),Tt.copy(ct.boundingSphere.center)),Tt.applyMatrix4(w.matrixWorld).applyMatrix4(pt)),Array.isArray(vt)){const yt=ct.groups;for(let Rt=0,Lt=yt.length;Rt<Lt;Rt++){const wt=yt[Rt],Qt=vt[wt.materialIndex];Qt&&Qt.visible&&v.push(w,ct,Qt,k,Tt.z,wt)}}else vt.visible&&v.push(w,ct,vt,k,Tt.z,null)}}const et=w.children;for(let ct=0,vt=et.length;ct<vt;ct++)ar(et[ct],U,k,H)}function to(w,U,k,H){const N=w.opaque,et=w.transmissive,ct=w.transparent;m.setupLightsView(k),W===!0&&tt.setGlobalState(_.clippingPlanes,k),H&&ut.viewport(x.copy(H)),N.length>0&&hs(N,U,k),et.length>0&&hs(et,U,k),ct.length>0&&hs(ct,U,k),ut.buffers.depth.setTest(!0),ut.buffers.depth.setMask(!0),ut.buffers.color.setMask(!0),ut.setPolygonOffset(!1)}function eo(w,U,k,H){if((k.isScene===!0?k.overrideMaterial:null)!==null)return;m.state.transmissionRenderTarget[H.id]===void 0&&(m.state.transmissionRenderTarget[H.id]=new $n(1,1,{generateMipmaps:!0,type:Ut.has("EXT_color_buffer_half_float")||Ut.has("EXT_color_buffer_float")?os:Mn,minFilter:jn,samples:4,stencilBuffer:r,resolveDepthBuffer:!1,resolveStencilBuffer:!1,colorSpace:Jt.workingColorSpace}));const et=m.state.transmissionRenderTarget[H.id],ct=H.viewport||x;et.setSize(ct.z,ct.w);const vt=_.getRenderTarget();_.setRenderTarget(et),_.getClearColor(V),K=_.getClearAlpha(),K<1&&_.setClearColor(16777215,.5),_.clear(),Kt&&Dt.render(k);const yt=_.toneMapping;_.toneMapping=Dn;const Rt=H.viewport;if(H.viewport!==void 0&&(H.viewport=void 0),m.setupLightsView(H),W===!0&&tt.setGlobalState(_.clippingPlanes,H),hs(w,k,H),b.updateMultisampleRenderTarget(et),b.updateRenderTargetMipmap(et),Ut.has("WEBGL_multisampled_render_to_texture")===!1){let Lt=!1;for(let wt=0,Qt=U.length;wt<Qt;wt++){const ie=U[wt],ae=ie.object,Ne=ie.geometry,Zt=ie.material,Et=ie.group;if(Zt.side===de&&ae.layers.test(H.layers)){const ve=Zt.side;Zt.side=Pe,Zt.needsUpdate=!0,no(ae,k,H,Ne,Zt,Et),Zt.side=ve,Zt.needsUpdate=!0,Lt=!0}}Lt===!0&&(b.updateMultisampleRenderTarget(et),b.updateRenderTargetMipmap(et))}_.setRenderTarget(vt),_.setClearColor(V,K),Rt!==void 0&&(H.viewport=Rt),_.toneMapping=yt}function hs(w,U,k){const H=U.isScene===!0?U.overrideMaterial:null;for(let N=0,et=w.length;N<et;N++){const ct=w[N],vt=ct.object,yt=ct.geometry,Rt=H===null?ct.material:H,Lt=ct.group;vt.layers.test(k.layers)&&no(vt,U,k,yt,Rt,Lt)}}function no(w,U,k,H,N,et){w.onBeforeRender(_,U,k,H,N,et),w.modelViewMatrix.multiplyMatrices(k.matrixWorldInverse,w.matrixWorld),w.normalMatrix.getNormalMatrix(w.modelViewMatrix),N.onBeforeRender(_,U,k,H,w,et),N.transparent===!0&&N.side===de&&N.forceSinglePass===!1?(N.side=Pe,N.needsUpdate=!0,_.renderBufferDirect(k,U,H,N,w,et),N.side=hn,N.needsUpdate=!0,_.renderBufferDirect(k,U,H,N,w,et),N.side=de):_.renderBufferDirect(k,U,H,N,w,et),w.onAfterRender(_,U,k,H,N,et)}function us(w,U,k){U.isScene!==!0&&(U=kt);const H=bt.get(w),N=m.state.lights,et=m.state.shadowsArray,ct=N.state.version,vt=St.getParameters(w,N.state,et,U,k),yt=St.getProgramCacheKey(vt);let Rt=H.programs;H.environment=w.isMeshStandardMaterial?U.environment:null,H.fog=U.fog,H.envMap=(w.isMeshStandardMaterial?B:M).get(w.envMap||H.environment),H.envMapRotation=H.environment!==null&&w.envMap===null?U.environmentRotation:w.envMapRotation,Rt===void 0&&(w.addEventListener("dispose",Xt),Rt=new Map,H.programs=Rt);let Lt=Rt.get(yt);if(Lt!==void 0){if(H.currentProgram===Lt&&H.lightsStateVersion===ct)return so(w,vt),Lt}else vt.uniforms=St.getUniforms(w),w.onBeforeCompile(vt,_),Lt=St.acquireProgram(vt,yt),Rt.set(yt,Lt),H.uniforms=vt.uniforms;const wt=H.uniforms;return(!w.isShaderMaterial&&!w.isRawShaderMaterial||w.clipping===!0)&&(wt.clippingPlanes=tt.uniform),so(w,vt),H.needsLights=xc(w),H.lightsStateVersion=ct,H.needsLights&&(wt.ambientLightColor.value=N.state.ambient,wt.lightProbe.value=N.state.probe,wt.directionalLights.value=N.state.directional,wt.directionalLightShadows.value=N.state.directionalShadow,wt.spotLights.value=N.state.spot,wt.spotLightShadows.value=N.state.spotShadow,wt.rectAreaLights.value=N.state.rectArea,wt.ltc_1.value=N.state.rectAreaLTC1,wt.ltc_2.value=N.state.rectAreaLTC2,wt.pointLights.value=N.state.point,wt.pointLightShadows.value=N.state.pointShadow,wt.hemisphereLights.value=N.state.hemi,wt.directionalShadowMap.value=N.state.directionalShadowMap,wt.directionalShadowMatrix.value=N.state.directionalShadowMatrix,wt.spotShadowMap.value=N.state.spotShadowMap,wt.spotLightMatrix.value=N.state.spotLightMatrix,wt.spotLightMap.value=N.state.spotLightMap,wt.pointShadowMap.value=N.state.pointShadowMap,wt.pointShadowMatrix.value=N.state.pointShadowMatrix),H.currentProgram=Lt,H.uniformsList=null,Lt}function io(w){if(w.uniformsList===null){const U=w.currentProgram.getUniforms();w.uniformsList=Ys.seqWithValue(U.seq,w.uniforms)}return w.uniformsList}function so(w,U){const k=bt.get(w);k.outputColorSpace=U.outputColorSpace,k.batching=U.batching,k.batchingColor=U.batchingColor,k.instancing=U.instancing,k.instancingColor=U.instancingColor,k.instancingMorph=U.instancingMorph,k.skinning=U.skinning,k.morphTargets=U.morphTargets,k.morphNormals=U.morphNormals,k.morphColors=U.morphColors,k.morphTargetsCount=U.morphTargetsCount,k.numClippingPlanes=U.numClippingPlanes,k.numIntersection=U.numClipIntersection,k.vertexAlphas=U.vertexAlphas,k.vertexTangents=U.vertexTangents,k.toneMapping=U.toneMapping}function gc(w,U,k,H,N){U.isScene!==!0&&(U=kt),b.resetTextureUnits();const et=U.fog,ct=H.isMeshStandardMaterial?U.environment:null,vt=A===null?_.outputColorSpace:A.isXRRenderTarget===!0?A.texture.colorSpace:In,yt=(H.isMeshStandardMaterial?B:M).get(H.envMap||ct),Rt=H.vertexColors===!0&&!!k.attributes.color&&k.attributes.color.itemSize===4,Lt=!!k.attributes.tangent&&(!!H.normalMap||H.anisotropy>0),wt=!!k.morphAttributes.position,Qt=!!k.morphAttributes.normal,ie=!!k.morphAttributes.color;let ae=Dn;H.toneMapped&&(A===null||A.isXRRenderTarget===!0)&&(ae=_.toneMapping);const Ne=k.morphAttributes.position||k.morphAttributes.normal||k.morphAttributes.color,Zt=Ne!==void 0?Ne.length:0,Et=bt.get(H),ve=m.state.lights;if(W===!0&&(J===!0||w!==q)){const Ye=w===q&&H.id===L;tt.setState(H,w,Ye)}let $t=!1;H.version===Et.__version?(Et.needsLights&&Et.lightsStateVersion!==ve.state.version||Et.outputColorSpace!==vt||N.isBatchedMesh&&Et.batching===!1||!N.isBatchedMesh&&Et.batching===!0||N.isBatchedMesh&&Et.batchingColor===!0&&N.colorTexture===null||N.isBatchedMesh&&Et.batchingColor===!1&&N.colorTexture!==null||N.isInstancedMesh&&Et.instancing===!1||!N.isInstancedMesh&&Et.instancing===!0||N.isSkinnedMesh&&Et.skinning===!1||!N.isSkinnedMesh&&Et.skinning===!0||N.isInstancedMesh&&Et.instancingColor===!0&&N.instanceColor===null||N.isInstancedMesh&&Et.instancingColor===!1&&N.instanceColor!==null||N.isInstancedMesh&&Et.instancingMorph===!0&&N.morphTexture===null||N.isInstancedMesh&&Et.instancingMorph===!1&&N.morphTexture!==null||Et.envMap!==yt||H.fog===!0&&Et.fog!==et||Et.numClippingPlanes!==void 0&&(Et.numClippingPlanes!==tt.numPlanes||Et.numIntersection!==tt.numIntersection)||Et.vertexAlphas!==Rt||Et.vertexTangents!==Lt||Et.morphTargets!==wt||Et.morphNormals!==Qt||Et.morphColors!==ie||Et.toneMapping!==ae||Et.morphTargetsCount!==Zt)&&($t=!0):($t=!0,Et.__version=H.version);let $e=Et.currentProgram;$t===!0&&($e=us(H,U,N));let ei=!1,Fe=!1,or=!1;const ce=$e.getUniforms(),yn=Et.uniforms;if(ut.useProgram($e.program)&&(ei=!0,Fe=!0,or=!0),H.id!==L&&(L=H.id,Fe=!0),ei||q!==w){Gt.reverseDepthBuffer?(it.copy(w.projectionMatrix),Lh(it),Dh(it),ce.setValue(C,"projectionMatrix",it)):ce.setValue(C,"projectionMatrix",w.projectionMatrix),ce.setValue(C,"viewMatrix",w.matrixWorldInverse);const Ye=ce.map.cameraPosition;Ye!==void 0&&Ye.setValue(C,mt.setFromMatrixPosition(w.matrixWorld)),Gt.logarithmicDepthBuffer&&ce.setValue(C,"logDepthBufFC",2/(Math.log(w.far+1)/Math.LN2)),(H.isMeshPhongMaterial||H.isMeshToonMaterial||H.isMeshLambertMaterial||H.isMeshBasicMaterial||H.isMeshStandardMaterial||H.isShaderMaterial)&&ce.setValue(C,"isOrthographic",w.isOrthographicCamera===!0),q!==w&&(q=w,Fe=!0,or=!0)}if(N.isSkinnedMesh){ce.setOptional(C,N,"bindMatrix"),ce.setOptional(C,N,"bindMatrixInverse");const Ye=N.skeleton;Ye&&(Ye.boneTexture===null&&Ye.computeBoneTexture(),ce.setValue(C,"boneTexture",Ye.boneTexture,b))}N.isBatchedMesh&&(ce.setOptional(C,N,"batchingTexture"),ce.setValue(C,"batchingTexture",N._matricesTexture,b),ce.setOptional(C,N,"batchingIdTexture"),ce.setValue(C,"batchingIdTexture",N._indirectTexture,b),ce.setOptional(C,N,"batchingColorTexture"),N._colorsTexture!==null&&ce.setValue(C,"batchingColorTexture",N._colorsTexture,b));const lr=k.morphAttributes;if((lr.position!==void 0||lr.normal!==void 0||lr.color!==void 0)&&It.update(N,k,$e),(Fe||Et.receiveShadow!==N.receiveShadow)&&(Et.receiveShadow=N.receiveShadow,ce.setValue(C,"receiveShadow",N.receiveShadow)),H.isMeshGouraudMaterial&&H.envMap!==null&&(yn.envMap.value=yt,yn.flipEnvMap.value=yt.isCubeTexture&&yt.isRenderTargetTexture===!1?-1:1),H.isMeshStandardMaterial&&H.envMap===null&&U.environment!==null&&(yn.envMapIntensity.value=U.environmentIntensity),Fe&&(ce.setValue(C,"toneMappingExposure",_.toneMappingExposure),Et.needsLights&&_c(yn,or),et&&H.fog===!0&&at.refreshFogUniforms(yn,et),at.refreshMaterialUniforms(yn,H,F,I,m.state.transmissionRenderTarget[w.id]),Ys.upload(C,io(Et),yn,b)),H.isShaderMaterial&&H.uniformsNeedUpdate===!0&&(Ys.upload(C,io(Et),yn,b),H.uniformsNeedUpdate=!1),H.isSpriteMaterial&&ce.setValue(C,"center",N.center),ce.setValue(C,"modelViewMatrix",N.modelViewMatrix),ce.setValue(C,"normalMatrix",N.normalMatrix),ce.setValue(C,"modelMatrix",N.matrixWorld),H.isShaderMaterial||H.isRawShaderMaterial){const Ye=H.uniformsGroups;for(let cr=0,vc=Ye.length;cr<vc;cr++){const ro=Ye[cr];D.update(ro,$e),D.bind(ro,$e)}}return $e}function _c(w,U){w.ambientLightColor.needsUpdate=U,w.lightProbe.needsUpdate=U,w.directionalLights.needsUpdate=U,w.directionalLightShadows.needsUpdate=U,w.pointLights.needsUpdate=U,w.pointLightShadows.needsUpdate=U,w.spotLights.needsUpdate=U,w.spotLightShadows.needsUpdate=U,w.rectAreaLights.needsUpdate=U,w.hemisphereLights.needsUpdate=U}function xc(w){return w.isMeshLambertMaterial||w.isMeshToonMaterial||w.isMeshPhongMaterial||w.isMeshStandardMaterial||w.isShadowMaterial||w.isShaderMaterial&&w.lights===!0}this.getActiveCubeFace=function(){return P},this.getActiveMipmapLevel=function(){return T},this.getRenderTarget=function(){return A},this.setRenderTargetTextures=function(w,U,k){bt.get(w.texture).__webglTexture=U,bt.get(w.depthTexture).__webglTexture=k;const H=bt.get(w);H.__hasExternalTextures=!0,H.__autoAllocateDepthBuffer=k===void 0,H.__autoAllocateDepthBuffer||Ut.has("WEBGL_multisampled_render_to_texture")===!0&&(console.warn("THREE.WebGLRenderer: Render-to-texture extension was disabled because an external texture was provided"),H.__useRenderToTexture=!1)},this.setRenderTargetFramebuffer=function(w,U){const k=bt.get(w);k.__webglFramebuffer=U,k.__useDefaultFramebuffer=U===void 0},this.setRenderTarget=function(w,U=0,k=0){A=w,P=U,T=k;let H=!0,N=null,et=!1,ct=!1;if(w){const yt=bt.get(w);if(yt.__useDefaultFramebuffer!==void 0)ut.bindFramebuffer(C.FRAMEBUFFER,null),H=!1;else if(yt.__webglFramebuffer===void 0)b.setupRenderTarget(w);else if(yt.__hasExternalTextures)b.rebindTextures(w,bt.get(w.texture).__webglTexture,bt.get(w.depthTexture).__webglTexture);else if(w.depthBuffer){const wt=w.depthTexture;if(yt.__boundDepthTexture!==wt){if(wt!==null&&bt.has(wt)&&(w.width!==wt.image.width||w.height!==wt.image.height))throw new Error("WebGLRenderTarget: Attached DepthTexture is initialized to the incorrect size.");b.setupDepthRenderbuffer(w)}}const Rt=w.texture;(Rt.isData3DTexture||Rt.isDataArrayTexture||Rt.isCompressedArrayTexture)&&(ct=!0);const Lt=bt.get(w).__webglFramebuffer;w.isWebGLCubeRenderTarget?(Array.isArray(Lt[U])?N=Lt[U][k]:N=Lt[U],et=!0):w.samples>0&&b.useMultisampledRTT(w)===!1?N=bt.get(w).__webglMultisampledFramebuffer:Array.isArray(Lt)?N=Lt[k]:N=Lt,x.copy(w.viewport),E.copy(w.scissor),z=w.scissorTest}else x.copy(nt).multiplyScalar(F).floor(),E.copy(rt).multiplyScalar(F).floor(),z=ht;if(ut.bindFramebuffer(C.FRAMEBUFFER,N)&&H&&ut.drawBuffers(w,N),ut.viewport(x),ut.scissor(E),ut.setScissorTest(z),et){const yt=bt.get(w.texture);C.framebufferTexture2D(C.FRAMEBUFFER,C.COLOR_ATTACHMENT0,C.TEXTURE_CUBE_MAP_POSITIVE_X+U,yt.__webglTexture,k)}else if(ct){const yt=bt.get(w.texture),Rt=U||0;C.framebufferTextureLayer(C.FRAMEBUFFER,C.COLOR_ATTACHMENT0,yt.__webglTexture,k||0,Rt)}L=-1},this.readRenderTargetPixels=function(w,U,k,H,N,et,ct){if(!(w&&w.isWebGLRenderTarget)){console.error("THREE.WebGLRenderer.readRenderTargetPixels: renderTarget is not THREE.WebGLRenderTarget.");return}let vt=bt.get(w).__webglFramebuffer;if(w.isWebGLCubeRenderTarget&&ct!==void 0&&(vt=vt[ct]),vt){ut.bindFramebuffer(C.FRAMEBUFFER,vt);try{const yt=w.texture,Rt=yt.format,Lt=yt.type;if(!Gt.textureFormatReadable(Rt)){console.error("THREE.WebGLRenderer.readRenderTargetPixels: renderTarget is not in RGBA or implementation defined format.");return}if(!Gt.textureTypeReadable(Lt)){console.error("THREE.WebGLRenderer.readRenderTargetPixels: renderTarget is not in UnsignedByteType or implementation defined type.");return}U>=0&&U<=w.width-H&&k>=0&&k<=w.height-N&&C.readPixels(U,k,H,N,Nt.convert(Rt),Nt.convert(Lt),et)}finally{const yt=A!==null?bt.get(A).__webglFramebuffer:null;ut.bindFramebuffer(C.FRAMEBUFFER,yt)}}},this.readRenderTargetPixelsAsync=async function(w,U,k,H,N,et,ct){if(!(w&&w.isWebGLRenderTarget))throw new Error("THREE.WebGLRenderer.readRenderTargetPixels: renderTarget is not THREE.WebGLRenderTarget.");let vt=bt.get(w).__webglFramebuffer;if(w.isWebGLCubeRenderTarget&&ct!==void 0&&(vt=vt[ct]),vt){const yt=w.texture,Rt=yt.format,Lt=yt.type;if(!Gt.textureFormatReadable(Rt))throw new Error("THREE.WebGLRenderer.readRenderTargetPixelsAsync: renderTarget is not in RGBA or implementation defined format.");if(!Gt.textureTypeReadable(Lt))throw new Error("THREE.WebGLRenderer.readRenderTargetPixelsAsync: renderTarget is not in UnsignedByteType or implementation defined type.");if(U>=0&&U<=w.width-H&&k>=0&&k<=w.height-N){ut.bindFramebuffer(C.FRAMEBUFFER,vt);const wt=C.createBuffer();C.bindBuffer(C.PIXEL_PACK_BUFFER,wt),C.bufferData(C.PIXEL_PACK_BUFFER,et.byteLength,C.STREAM_READ),C.readPixels(U,k,H,N,Nt.convert(Rt),Nt.convert(Lt),0);const Qt=A!==null?bt.get(A).__webglFramebuffer:null;ut.bindFramebuffer(C.FRAMEBUFFER,Qt);const ie=C.fenceSync(C.SYNC_GPU_COMMANDS_COMPLETE,0);return C.flush(),await Ph(C,ie,4),C.bindBuffer(C.PIXEL_PACK_BUFFER,wt),C.getBufferSubData(C.PIXEL_PACK_BUFFER,0,et),C.deleteBuffer(wt),C.deleteSync(ie),et}else throw new Error("THREE.WebGLRenderer.readRenderTargetPixelsAsync: requested read bounds are out of range.")}},this.copyFramebufferToTexture=function(w,U=null,k=0){w.isTexture!==!0&&(Xs("WebGLRenderer: copyFramebufferToTexture function signature has changed."),U=arguments[0]||null,w=arguments[1]);const H=Math.pow(2,-k),N=Math.floor(w.image.width*H),et=Math.floor(w.image.height*H),ct=U!==null?U.x:0,vt=U!==null?U.y:0;b.setTexture2D(w,0),C.copyTexSubImage2D(C.TEXTURE_2D,k,0,0,ct,vt,N,et),ut.unbindTexture()},this.copyTextureToTexture=function(w,U,k=null,H=null,N=0){w.isTexture!==!0&&(Xs("WebGLRenderer: copyTextureToTexture function signature has changed."),H=arguments[0]||null,w=arguments[1],U=arguments[2],N=arguments[3]||0,k=null);let et,ct,vt,yt,Rt,Lt;k!==null?(et=k.max.x-k.min.x,ct=k.max.y-k.min.y,vt=k.min.x,yt=k.min.y):(et=w.image.width,ct=w.image.height,vt=0,yt=0),H!==null?(Rt=H.x,Lt=H.y):(Rt=0,Lt=0);const wt=Nt.convert(U.format),Qt=Nt.convert(U.type);b.setTexture2D(U,0),C.pixelStorei(C.UNPACK_FLIP_Y_WEBGL,U.flipY),C.pixelStorei(C.UNPACK_PREMULTIPLY_ALPHA_WEBGL,U.premultiplyAlpha),C.pixelStorei(C.UNPACK_ALIGNMENT,U.unpackAlignment);const ie=C.getParameter(C.UNPACK_ROW_LENGTH),ae=C.getParameter(C.UNPACK_IMAGE_HEIGHT),Ne=C.getParameter(C.UNPACK_SKIP_PIXELS),Zt=C.getParameter(C.UNPACK_SKIP_ROWS),Et=C.getParameter(C.UNPACK_SKIP_IMAGES),ve=w.isCompressedTexture?w.mipmaps[N]:w.image;C.pixelStorei(C.UNPACK_ROW_LENGTH,ve.width),C.pixelStorei(C.UNPACK_IMAGE_HEIGHT,ve.height),C.pixelStorei(C.UNPACK_SKIP_PIXELS,vt),C.pixelStorei(C.UNPACK_SKIP_ROWS,yt),w.isDataTexture?C.texSubImage2D(C.TEXTURE_2D,N,Rt,Lt,et,ct,wt,Qt,ve.data):w.isCompressedTexture?C.compressedTexSubImage2D(C.TEXTURE_2D,N,Rt,Lt,ve.width,ve.height,wt,ve.data):C.texSubImage2D(C.TEXTURE_2D,N,Rt,Lt,et,ct,wt,Qt,ve),C.pixelStorei(C.UNPACK_ROW_LENGTH,ie),C.pixelStorei(C.UNPACK_IMAGE_HEIGHT,ae),C.pixelStorei(C.UNPACK_SKIP_PIXELS,Ne),C.pixelStorei(C.UNPACK_SKIP_ROWS,Zt),C.pixelStorei(C.UNPACK_SKIP_IMAGES,Et),N===0&&U.generateMipmaps&&C.generateMipmap(C.TEXTURE_2D),ut.unbindTexture()},this.copyTextureToTexture3D=function(w,U,k=null,H=null,N=0){w.isTexture!==!0&&(Xs("WebGLRenderer: copyTextureToTexture3D function signature has changed."),k=arguments[0]||null,H=arguments[1]||null,w=arguments[2],U=arguments[3],N=arguments[4]||0);let et,ct,vt,yt,Rt,Lt,wt,Qt,ie;const ae=w.isCompressedTexture?w.mipmaps[N]:w.image;k!==null?(et=k.max.x-k.min.x,ct=k.max.y-k.min.y,vt=k.max.z-k.min.z,yt=k.min.x,Rt=k.min.y,Lt=k.min.z):(et=ae.width,ct=ae.height,vt=ae.depth,yt=0,Rt=0,Lt=0),H!==null?(wt=H.x,Qt=H.y,ie=H.z):(wt=0,Qt=0,ie=0);const Ne=Nt.convert(U.format),Zt=Nt.convert(U.type);let Et;if(U.isData3DTexture)b.setTexture3D(U,0),Et=C.TEXTURE_3D;else if(U.isDataArrayTexture||U.isCompressedArrayTexture)b.setTexture2DArray(U,0),Et=C.TEXTURE_2D_ARRAY;else{console.warn("THREE.WebGLRenderer.copyTextureToTexture3D: only supports THREE.DataTexture3D and THREE.DataTexture2DArray.");return}C.pixelStorei(C.UNPACK_FLIP_Y_WEBGL,U.flipY),C.pixelStorei(C.UNPACK_PREMULTIPLY_ALPHA_WEBGL,U.premultiplyAlpha),C.pixelStorei(C.UNPACK_ALIGNMENT,U.unpackAlignment);const ve=C.getParameter(C.UNPACK_ROW_LENGTH),$t=C.getParameter(C.UNPACK_IMAGE_HEIGHT),$e=C.getParameter(C.UNPACK_SKIP_PIXELS),ei=C.getParameter(C.UNPACK_SKIP_ROWS),Fe=C.getParameter(C.UNPACK_SKIP_IMAGES);C.pixelStorei(C.UNPACK_ROW_LENGTH,ae.width),C.pixelStorei(C.UNPACK_IMAGE_HEIGHT,ae.height),C.pixelStorei(C.UNPACK_SKIP_PIXELS,yt),C.pixelStorei(C.UNPACK_SKIP_ROWS,Rt),C.pixelStorei(C.UNPACK_SKIP_IMAGES,Lt),w.isDataTexture||w.isData3DTexture?C.texSubImage3D(Et,N,wt,Qt,ie,et,ct,vt,Ne,Zt,ae.data):U.isCompressedArrayTexture?C.compressedTexSubImage3D(Et,N,wt,Qt,ie,et,ct,vt,Ne,ae.data):C.texSubImage3D(Et,N,wt,Qt,ie,et,ct,vt,Ne,Zt,ae),C.pixelStorei(C.UNPACK_ROW_LENGTH,ve),C.pixelStorei(C.UNPACK_IMAGE_HEIGHT,$t),C.pixelStorei(C.UNPACK_SKIP_PIXELS,$e),C.pixelStorei(C.UNPACK_SKIP_ROWS,ei),C.pixelStorei(C.UNPACK_SKIP_IMAGES,Fe),N===0&&U.generateMipmaps&&C.generateMipmap(Et),ut.unbindTexture()},this.initRenderTarget=function(w){bt.get(w).__webglFramebuffer===void 0&&b.setupRenderTarget(w)},this.initTexture=function(w){w.isCubeTexture?b.setTextureCube(w,0):w.isData3DTexture?b.setTexture3D(w,0):w.isDataArrayTexture||w.isCompressedArrayTexture?b.setTexture2DArray(w,0):b.setTexture2D(w,0),ut.unbindTexture()},this.resetState=function(){P=0,T=0,A=null,ut.reset(),ne.reset()},typeof __THREE_DEVTOOLS__<"u"&&__THREE_DEVTOOLS__.dispatchEvent(new CustomEvent("observe",{detail:this}))}get coordinateSystem(){return vn}get outputColorSpace(){return this._outputColorSpace}set outputColorSpace(t){this._outputColorSpace=t;const e=this.getContext();e.drawingBufferColorSpace=t===Va?"display-p3":"srgb",e.unpackColorSpace=Jt.workingColorSpace===ir?"display-p3":"srgb"}}class ja{constructor(t,e=25e-5){this.isFogExp2=!0,this.name="",this.color=new Pt(t),this.density=e}clone(){return new ja(this.color,this.density)}toJSON(){return{type:"FogExp2",name:this.name,color:this.color.getHex(),density:this.density}}}class Wm extends me{constructor(){super(),this.isScene=!0,this.type="Scene",this.background=null,this.environment=null,this.fog=null,this.backgroundBlurriness=0,this.backgroundIntensity=1,this.backgroundRotation=new on,this.environmentIntensity=1,this.environmentRotation=new on,this.overrideMaterial=null,typeof __THREE_DEVTOOLS__<"u"&&__THREE_DEVTOOLS__.dispatchEvent(new CustomEvent("observe",{detail:this}))}copy(t,e){return super.copy(t,e),t.background!==null&&(this.background=t.background.clone()),t.environment!==null&&(this.environment=t.environment.clone()),t.fog!==null&&(this.fog=t.fog.clone()),this.backgroundBlurriness=t.backgroundBlurriness,this.backgroundIntensity=t.backgroundIntensity,this.backgroundRotation.copy(t.backgroundRotation),this.environmentIntensity=t.environmentIntensity,this.environmentRotation.copy(t.environmentRotation),t.overrideMaterial!==null&&(this.overrideMaterial=t.overrideMaterial.clone()),this.matrixAutoUpdate=t.matrixAutoUpdate,this}toJSON(t){const e=super.toJSON(t);return this.fog!==null&&(e.object.fog=this.fog.toJSON()),this.backgroundBlurriness>0&&(e.object.backgroundBlurriness=this.backgroundBlurriness),this.backgroundIntensity!==1&&(e.object.backgroundIntensity=this.backgroundIntensity),e.object.backgroundRotation=this.backgroundRotation.toArray(),this.environmentIntensity!==1&&(e.object.environmentIntensity=this.environmentIntensity),e.object.environmentRotation=this.environmentRotation.toArray(),e}}class Xm extends be{constructor(t=null,e=1,n=1,s,r,a,o,l,h=Ue,d=Ue,c,u){super(null,a,o,l,h,d,s,r,c,u),this.isDataTexture=!0,this.image={data:t,width:e,height:n},this.generateMipmaps=!1,this.flipY=!1,this.unpackAlignment=1}}class el extends Xe{constructor(t,e,n,s=1){super(t,e,n),this.isInstancedBufferAttribute=!0,this.meshPerAttribute=s}copy(t){return super.copy(t),this.meshPerAttribute=t.meshPerAttribute,this}toJSON(){const t=super.toJSON();return t.meshPerAttribute=this.meshPerAttribute,t.isInstancedBufferAttribute=!0,t}}const gi=new ee,nl=new ee,Is=[],il=new Un,Ym=new ee,Xi=new Ct,Yi=new Oi;class qm extends Ct{constructor(t,e,n){super(t,e),this.isInstancedMesh=!0,this.instanceMatrix=new el(new Float32Array(n*16),16),this.instanceColor=null,this.morphTexture=null,this.count=n,this.boundingBox=null,this.boundingSphere=null;for(let s=0;s<n;s++)this.setMatrixAt(s,Ym)}computeBoundingBox(){const t=this.geometry,e=this.count;this.boundingBox===null&&(this.boundingBox=new Un),t.boundingBox===null&&t.computeBoundingBox(),this.boundingBox.makeEmpty();for(let n=0;n<e;n++)this.getMatrixAt(n,gi),il.copy(t.boundingBox).applyMatrix4(gi),this.boundingBox.union(il)}computeBoundingSphere(){const t=this.geometry,e=this.count;this.boundingSphere===null&&(this.boundingSphere=new Oi),t.boundingSphere===null&&t.computeBoundingSphere(),this.boundingSphere.makeEmpty();for(let n=0;n<e;n++)this.getMatrixAt(n,gi),Yi.copy(t.boundingSphere).applyMatrix4(gi),this.boundingSphere.union(Yi)}copy(t,e){return super.copy(t,e),this.instanceMatrix.copy(t.instanceMatrix),t.morphTexture!==null&&(this.morphTexture=t.morphTexture.clone()),t.instanceColor!==null&&(this.instanceColor=t.instanceColor.clone()),this.count=t.count,t.boundingBox!==null&&(this.boundingBox=t.boundingBox.clone()),t.boundingSphere!==null&&(this.boundingSphere=t.boundingSphere.clone()),this}getColorAt(t,e){e.fromArray(this.instanceColor.array,t*3)}getMatrixAt(t,e){e.fromArray(this.instanceMatrix.array,t*16)}getMorphAt(t,e){const n=e.morphTargetInfluences,s=this.morphTexture.source.data.data,r=n.length+1,a=t*r+1;for(let o=0;o<n.length;o++)n[o]=s[a+o]}raycast(t,e){const n=this.matrixWorld,s=this.count;if(Xi.geometry=this.geometry,Xi.material=this.material,Xi.material!==void 0&&(this.boundingSphere===null&&this.computeBoundingSphere(),Yi.copy(this.boundingSphere),Yi.applyMatrix4(n),t.ray.intersectsSphere(Yi)!==!1))for(let r=0;r<s;r++){this.getMatrixAt(r,gi),nl.multiplyMatrices(n,gi),Xi.matrixWorld=nl,Xi.raycast(t,Is);for(let a=0,o=Is.length;a<o;a++){const l=Is[a];l.instanceId=r,l.object=this,e.push(l)}Is.length=0}}setColorAt(t,e){this.instanceColor===null&&(this.instanceColor=new el(new Float32Array(this.instanceMatrix.count*3).fill(1),3)),e.toArray(this.instanceColor.array,t*3)}setMatrixAt(t,e){e.toArray(this.instanceMatrix.array,t*16)}setMorphAt(t,e){const n=e.morphTargetInfluences,s=n.length+1;this.morphTexture===null&&(this.morphTexture=new Xm(new Float32Array(s*this.count),s,this.count,ka,cn));const r=this.morphTexture.source.data.data;let a=0;for(let h=0;h<n.length;h++)a+=n[h];const o=this.geometry.morphTargetsRelative?1:1-a,l=s*t;r[l]=o,r.set(n,l+1)}updateMorphTargets(){}dispose(){return this.dispatchEvent({type:"dispose"}),this.morphTexture!==null&&(this.morphTexture.dispose(),this.morphTexture=null),this}}class oc extends Bi{constructor(t){super(),this.isPointsMaterial=!0,this.type="PointsMaterial",this.color=new Pt(16777215),this.map=null,this.alphaMap=null,this.size=1,this.sizeAttenuation=!0,this.fog=!0,this.setValues(t)}copy(t){return super.copy(t),this.color.copy(t.color),this.map=t.map,this.alphaMap=t.alphaMap,this.size=t.size,this.sizeAttenuation=t.sizeAttenuation,this.fog=t.fog,this}}const sl=new ee,Da=new Xa,Us=new Oi,Ns=new R;class Km extends me{constructor(t=new Le,e=new oc){super(),this.isPoints=!0,this.type="Points",this.geometry=t,this.material=e,this.updateMorphTargets()}copy(t,e){return super.copy(t,e),this.material=Array.isArray(t.material)?t.material.slice():t.material,this.geometry=t.geometry,this}raycast(t,e){const n=this.geometry,s=this.matrixWorld,r=t.params.Points.threshold,a=n.drawRange;if(n.boundingSphere===null&&n.computeBoundingSphere(),Us.copy(n.boundingSphere),Us.applyMatrix4(s),Us.radius+=r,t.ray.intersectsSphere(Us)===!1)return;sl.copy(s).invert(),Da.copy(t.ray).applyMatrix4(sl);const o=r/((this.scale.x+this.scale.y+this.scale.z)/3),l=o*o,h=n.index,c=n.attributes.position;if(h!==null){const u=Math.max(0,a.start),f=Math.min(h.count,a.start+a.count);for(let g=u,v=f;g<v;g++){const m=h.getX(g);Ns.fromBufferAttribute(c,m),rl(Ns,m,l,s,t,e,this)}}else{const u=Math.max(0,a.start),f=Math.min(c.count,a.start+a.count);for(let g=u,v=f;g<v;g++)Ns.fromBufferAttribute(c,g),rl(Ns,g,l,s,t,e,this)}}updateMorphTargets(){const e=this.geometry.morphAttributes,n=Object.keys(e);if(n.length>0){const s=e[n[0]];if(s!==void 0){this.morphTargetInfluences=[],this.morphTargetDictionary={};for(let r=0,a=s.length;r<a;r++){const o=s[r].name||String(r);this.morphTargetInfluences.push(0),this.morphTargetDictionary[o]=r}}}}}function rl(i,t,e,n,s,r,a){const o=Da.distanceSqToPoint(i);if(o<e){const l=new R;Da.closestPointToPoint(i,l),l.applyMatrix4(n);const h=s.ray.origin.distanceTo(l);if(h<s.near||h>s.far)return;r.push({distance:h,distanceToRay:Math.sqrt(o),point:l,index:t,face:null,faceIndex:null,barycoord:null,object:a})}}class Za extends be{constructor(t,e,n,s,r,a,o,l,h){super(t,e,n,s,r,a,o,l,h),this.isCanvasTexture=!0,this.needsUpdate=!0}}class Jn extends Le{constructor(t=1,e=1,n=1,s=32,r=1,a=!1,o=0,l=Math.PI*2){super(),this.type="CylinderGeometry",this.parameters={radiusTop:t,radiusBottom:e,height:n,radialSegments:s,heightSegments:r,openEnded:a,thetaStart:o,thetaLength:l};const h=this;s=Math.floor(s),r=Math.floor(r);const d=[],c=[],u=[],f=[];let g=0;const v=[],m=n/2;let p=0;y(),a===!1&&(t>0&&_(!0),e>0&&_(!1)),this.setIndex(d),this.setAttribute("position",new le(c,3)),this.setAttribute("normal",new le(u,3)),this.setAttribute("uv",new le(f,2));function y(){const S=new R,P=new R;let T=0;const A=(e-t)/n;for(let L=0;L<=r;L++){const q=[],x=L/r,E=x*(e-t)+t;for(let z=0;z<=s;z++){const V=z/s,K=V*l+o,G=Math.sin(K),I=Math.cos(K);P.x=E*G,P.y=-x*n+m,P.z=E*I,c.push(P.x,P.y,P.z),S.set(G,A,I).normalize(),u.push(S.x,S.y,S.z),f.push(V,1-x),q.push(g++)}v.push(q)}for(let L=0;L<s;L++)for(let q=0;q<r;q++){const x=v[q][L],E=v[q+1][L],z=v[q+1][L+1],V=v[q][L+1];t>0&&(d.push(x,E,V),T+=3),e>0&&(d.push(E,z,V),T+=3)}h.addGroup(p,T,0),p+=T}function _(S){const P=g,T=new Ht,A=new R;let L=0;const q=S===!0?t:e,x=S===!0?1:-1;for(let z=1;z<=s;z++)c.push(0,m*x,0),u.push(0,x,0),f.push(.5,.5),g++;const E=g;for(let z=0;z<=s;z++){const K=z/s*l+o,G=Math.cos(K),I=Math.sin(K);A.x=q*I,A.y=m*x,A.z=q*G,c.push(A.x,A.y,A.z),u.push(0,x,0),T.x=G*.5+.5,T.y=I*.5*x+.5,f.push(T.x,T.y),g++}for(let z=0;z<s;z++){const V=P+z,K=E+z;S===!0?d.push(K,K+1,V):d.push(K+1,K,V),L+=3}h.addGroup(p,L,S===!0?1:2),p+=L}}copy(t){return super.copy(t),this.parameters=Object.assign({},t.parameters),this}static fromJSON(t){return new Jn(t.radiusTop,t.radiusBottom,t.height,t.radialSegments,t.heightSegments,t.openEnded,t.thetaStart,t.thetaLength)}}class $a extends Le{constructor(t=[],e=[],n=1,s=0){super(),this.type="PolyhedronGeometry",this.parameters={vertices:t,indices:e,radius:n,detail:s};const r=[],a=[];o(s),h(n),d(),this.setAttribute("position",new le(r,3)),this.setAttribute("normal",new le(r.slice(),3)),this.setAttribute("uv",new le(a,2)),s===0?this.computeVertexNormals():this.normalizeNormals();function o(y){const _=new R,S=new R,P=new R;for(let T=0;T<e.length;T+=3)f(e[T+0],_),f(e[T+1],S),f(e[T+2],P),l(_,S,P,y)}function l(y,_,S,P){const T=P+1,A=[];for(let L=0;L<=T;L++){A[L]=[];const q=y.clone().lerp(S,L/T),x=_.clone().lerp(S,L/T),E=T-L;for(let z=0;z<=E;z++)z===0&&L===T?A[L][z]=q:A[L][z]=q.clone().lerp(x,z/E)}for(let L=0;L<T;L++)for(let q=0;q<2*(T-L)-1;q++){const x=Math.floor(q/2);q%2===0?(u(A[L][x+1]),u(A[L+1][x]),u(A[L][x])):(u(A[L][x+1]),u(A[L+1][x+1]),u(A[L+1][x]))}}function h(y){const _=new R;for(let S=0;S<r.length;S+=3)_.x=r[S+0],_.y=r[S+1],_.z=r[S+2],_.normalize().multiplyScalar(y),r[S+0]=_.x,r[S+1]=_.y,r[S+2]=_.z}function d(){const y=new R;for(let _=0;_<r.length;_+=3){y.x=r[_+0],y.y=r[_+1],y.z=r[_+2];const S=m(y)/2/Math.PI+.5,P=p(y)/Math.PI+.5;a.push(S,1-P)}g(),c()}function c(){for(let y=0;y<a.length;y+=6){const _=a[y+0],S=a[y+2],P=a[y+4],T=Math.max(_,S,P),A=Math.min(_,S,P);T>.9&&A<.1&&(_<.2&&(a[y+0]+=1),S<.2&&(a[y+2]+=1),P<.2&&(a[y+4]+=1))}}function u(y){r.push(y.x,y.y,y.z)}function f(y,_){const S=y*3;_.x=t[S+0],_.y=t[S+1],_.z=t[S+2]}function g(){const y=new R,_=new R,S=new R,P=new R,T=new Ht,A=new Ht,L=new Ht;for(let q=0,x=0;q<r.length;q+=9,x+=6){y.set(r[q+0],r[q+1],r[q+2]),_.set(r[q+3],r[q+4],r[q+5]),S.set(r[q+6],r[q+7],r[q+8]),T.set(a[x+0],a[x+1]),A.set(a[x+2],a[x+3]),L.set(a[x+4],a[x+5]),P.copy(y).add(_).add(S).divideScalar(3);const E=m(P);v(T,x+0,y,E),v(A,x+2,_,E),v(L,x+4,S,E)}}function v(y,_,S,P){P<0&&y.x===1&&(a[_]=y.x-1),S.x===0&&S.z===0&&(a[_]=P/2/Math.PI+.5)}function m(y){return Math.atan2(y.z,-y.x)}function p(y){return Math.atan2(-y.y,Math.sqrt(y.x*y.x+y.z*y.z))}}copy(t){return super.copy(t),this.parameters=Object.assign({},t.parameters),this}static fromJSON(t){return new $a(t.vertices,t.indices,t.radius,t.details)}}class cs extends $a{constructor(t=1,e=0){const n=(1+Math.sqrt(5))/2,s=[-1,n,0,1,n,0,-1,-n,0,1,-n,0,0,-1,n,0,1,n,0,-1,-n,0,1,-n,n,0,-1,n,0,1,-n,0,-1,-n,0,1],r=[0,11,5,0,5,1,0,1,7,0,7,10,0,10,11,1,5,9,5,11,4,11,10,2,10,7,6,7,1,8,3,9,4,3,4,2,3,2,6,3,6,8,3,8,9,4,9,5,2,4,11,6,2,10,8,6,7,9,8,1];super(s,r,t,e),this.type="IcosahedronGeometry",this.parameters={radius:t,detail:e}}static fromJSON(t){return new cs(t.radius,t.detail)}}class Pn extends Le{constructor(t=1,e=32,n=16,s=0,r=Math.PI*2,a=0,o=Math.PI){super(),this.type="SphereGeometry",this.parameters={radius:t,widthSegments:e,heightSegments:n,phiStart:s,phiLength:r,thetaStart:a,thetaLength:o},e=Math.max(3,Math.floor(e)),n=Math.max(2,Math.floor(n));const l=Math.min(a+o,Math.PI);let h=0;const d=[],c=new R,u=new R,f=[],g=[],v=[],m=[];for(let p=0;p<=n;p++){const y=[],_=p/n;let S=0;p===0&&a===0?S=.5/e:p===n&&l===Math.PI&&(S=-.5/e);for(let P=0;P<=e;P++){const T=P/e;c.x=-t*Math.cos(s+T*r)*Math.sin(a+_*o),c.y=t*Math.cos(a+_*o),c.z=t*Math.sin(s+T*r)*Math.sin(a+_*o),g.push(c.x,c.y,c.z),u.copy(c).normalize(),v.push(u.x,u.y,u.z),m.push(T+S,1-_),y.push(h++)}d.push(y)}for(let p=0;p<n;p++)for(let y=0;y<e;y++){const _=d[p][y+1],S=d[p][y],P=d[p+1][y],T=d[p+1][y+1];(p!==0||a>0)&&f.push(_,S,T),(p!==n-1||l<Math.PI)&&f.push(S,P,T)}this.setIndex(f),this.setAttribute("position",new le(g,3)),this.setAttribute("normal",new le(v,3)),this.setAttribute("uv",new le(m,2))}copy(t){return super.copy(t),this.parameters=Object.assign({},t.parameters),this}static fromJSON(t){return new Pn(t.radius,t.widthSegments,t.heightSegments,t.phiStart,t.phiLength,t.thetaStart,t.thetaLength)}}class ti extends Le{constructor(t=1,e=.4,n=12,s=48,r=Math.PI*2){super(),this.type="TorusGeometry",this.parameters={radius:t,tube:e,radialSegments:n,tubularSegments:s,arc:r},n=Math.floor(n),s=Math.floor(s);const a=[],o=[],l=[],h=[],d=new R,c=new R,u=new R;for(let f=0;f<=n;f++)for(let g=0;g<=s;g++){const v=g/s*r,m=f/n*Math.PI*2;c.x=(t+e*Math.cos(m))*Math.cos(v),c.y=(t+e*Math.cos(m))*Math.sin(v),c.z=e*Math.sin(m),o.push(c.x,c.y,c.z),d.x=t*Math.cos(v),d.y=t*Math.sin(v),u.subVectors(c,d).normalize(),l.push(u.x,u.y,u.z),h.push(g/s),h.push(f/n)}for(let f=1;f<=n;f++)for(let g=1;g<=s;g++){const v=(s+1)*f+g-1,m=(s+1)*(f-1)+g-1,p=(s+1)*(f-1)+g,y=(s+1)*f+g;a.push(v,m,y),a.push(m,p,y)}this.setIndex(a),this.setAttribute("position",new le(o,3)),this.setAttribute("normal",new le(l,3)),this.setAttribute("uv",new le(h,2))}copy(t){return super.copy(t),this.parameters=Object.assign({},t.parameters),this}static fromJSON(t){return new ti(t.radius,t.tube,t.radialSegments,t.tubularSegments,t.arc)}}class Me extends Bi{constructor(t){super(),this.isMeshStandardMaterial=!0,this.defines={STANDARD:""},this.type="MeshStandardMaterial",this.color=new Pt(16777215),this.roughness=1,this.metalness=0,this.map=null,this.lightMap=null,this.lightMapIntensity=1,this.aoMap=null,this.aoMapIntensity=1,this.emissive=new Pt(0),this.emissiveIntensity=1,this.emissiveMap=null,this.bumpMap=null,this.bumpScale=1,this.normalMap=null,this.normalMapType=Vl,this.normalScale=new Ht(1,1),this.displacementMap=null,this.displacementScale=1,this.displacementBias=0,this.roughnessMap=null,this.metalnessMap=null,this.alphaMap=null,this.envMap=null,this.envMapRotation=new on,this.envMapIntensity=1,this.wireframe=!1,this.wireframeLinewidth=1,this.wireframeLinecap="round",this.wireframeLinejoin="round",this.flatShading=!1,this.fog=!0,this.setValues(t)}copy(t){return super.copy(t),this.defines={STANDARD:""},this.color.copy(t.color),this.roughness=t.roughness,this.metalness=t.metalness,this.map=t.map,this.lightMap=t.lightMap,this.lightMapIntensity=t.lightMapIntensity,this.aoMap=t.aoMap,this.aoMapIntensity=t.aoMapIntensity,this.emissive.copy(t.emissive),this.emissiveMap=t.emissiveMap,this.emissiveIntensity=t.emissiveIntensity,this.bumpMap=t.bumpMap,this.bumpScale=t.bumpScale,this.normalMap=t.normalMap,this.normalMapType=t.normalMapType,this.normalScale.copy(t.normalScale),this.displacementMap=t.displacementMap,this.displacementScale=t.displacementScale,this.displacementBias=t.displacementBias,this.roughnessMap=t.roughnessMap,this.metalnessMap=t.metalnessMap,this.alphaMap=t.alphaMap,this.envMap=t.envMap,this.envMapRotation.copy(t.envMapRotation),this.envMapIntensity=t.envMapIntensity,this.wireframe=t.wireframe,this.wireframeLinewidth=t.wireframeLinewidth,this.wireframeLinecap=t.wireframeLinecap,this.wireframeLinejoin=t.wireframeLinejoin,this.flatShading=t.flatShading,this.fog=t.fog,this}}class jm extends Me{constructor(t){super(),this.isMeshPhysicalMaterial=!0,this.defines={STANDARD:"",PHYSICAL:""},this.type="MeshPhysicalMaterial",this.anisotropyRotation=0,this.anisotropyMap=null,this.clearcoatMap=null,this.clearcoatRoughness=0,this.clearcoatRoughnessMap=null,this.clearcoatNormalScale=new Ht(1,1),this.clearcoatNormalMap=null,this.ior=1.5,Object.defineProperty(this,"reflectivity",{get:function(){return Ee(2.5*(this.ior-1)/(this.ior+1),0,1)},set:function(e){this.ior=(1+.4*e)/(1-.4*e)}}),this.iridescenceMap=null,this.iridescenceIOR=1.3,this.iridescenceThicknessRange=[100,400],this.iridescenceThicknessMap=null,this.sheenColor=new Pt(0),this.sheenColorMap=null,this.sheenRoughness=1,this.sheenRoughnessMap=null,this.transmissionMap=null,this.thickness=0,this.thicknessMap=null,this.attenuationDistance=1/0,this.attenuationColor=new Pt(1,1,1),this.specularIntensity=1,this.specularIntensityMap=null,this.specularColor=new Pt(1,1,1),this.specularColorMap=null,this._anisotropy=0,this._clearcoat=0,this._dispersion=0,this._iridescence=0,this._sheen=0,this._transmission=0,this.setValues(t)}get anisotropy(){return this._anisotropy}set anisotropy(t){this._anisotropy>0!=t>0&&this.version++,this._anisotropy=t}get clearcoat(){return this._clearcoat}set clearcoat(t){this._clearcoat>0!=t>0&&this.version++,this._clearcoat=t}get iridescence(){return this._iridescence}set iridescence(t){this._iridescence>0!=t>0&&this.version++,this._iridescence=t}get dispersion(){return this._dispersion}set dispersion(t){this._dispersion>0!=t>0&&this.version++,this._dispersion=t}get sheen(){return this._sheen}set sheen(t){this._sheen>0!=t>0&&this.version++,this._sheen=t}get transmission(){return this._transmission}set transmission(t){this._transmission>0!=t>0&&this.version++,this._transmission=t}copy(t){return super.copy(t),this.defines={STANDARD:"",PHYSICAL:""},this.anisotropy=t.anisotropy,this.anisotropyRotation=t.anisotropyRotation,this.anisotropyMap=t.anisotropyMap,this.clearcoat=t.clearcoat,this.clearcoatMap=t.clearcoatMap,this.clearcoatRoughness=t.clearcoatRoughness,this.clearcoatRoughnessMap=t.clearcoatRoughnessMap,this.clearcoatNormalMap=t.clearcoatNormalMap,this.clearcoatNormalScale.copy(t.clearcoatNormalScale),this.dispersion=t.dispersion,this.ior=t.ior,this.iridescence=t.iridescence,this.iridescenceMap=t.iridescenceMap,this.iridescenceIOR=t.iridescenceIOR,this.iridescenceThicknessRange=[...t.iridescenceThicknessRange],this.iridescenceThicknessMap=t.iridescenceThicknessMap,this.sheen=t.sheen,this.sheenColor.copy(t.sheenColor),this.sheenColorMap=t.sheenColorMap,this.sheenRoughness=t.sheenRoughness,this.sheenRoughnessMap=t.sheenRoughnessMap,this.transmission=t.transmission,this.transmissionMap=t.transmissionMap,this.thickness=t.thickness,this.thicknessMap=t.thicknessMap,this.attenuationDistance=t.attenuationDistance,this.attenuationColor.copy(t.attenuationColor),this.specularIntensity=t.specularIntensity,this.specularIntensityMap=t.specularIntensityMap,this.specularColor.copy(t.specularColor),this.specularColorMap=t.specularColorMap,this}}class rr extends me{constructor(t,e=1){super(),this.isLight=!0,this.type="Light",this.color=new Pt(t),this.intensity=e}dispose(){}copy(t,e){return super.copy(t,e),this.color.copy(t.color),this.intensity=t.intensity,this}toJSON(t){const e=super.toJSON(t);return e.object.color=this.color.getHex(),e.object.intensity=this.intensity,this.groundColor!==void 0&&(e.object.groundColor=this.groundColor.getHex()),this.distance!==void 0&&(e.object.distance=this.distance),this.angle!==void 0&&(e.object.angle=this.angle),this.decay!==void 0&&(e.object.decay=this.decay),this.penumbra!==void 0&&(e.object.penumbra=this.penumbra),this.shadow!==void 0&&(e.object.shadow=this.shadow.toJSON()),this.target!==void 0&&(e.object.target=this.target.uuid),e}}class Zm extends rr{constructor(t,e,n){super(t,n),this.isHemisphereLight=!0,this.type="HemisphereLight",this.position.copy(me.DEFAULT_UP),this.updateMatrix(),this.groundColor=new Pt(e)}copy(t,e){return super.copy(t,e),this.groundColor.copy(t.groundColor),this}}const Hr=new ee,al=new R,ol=new R;class lc{constructor(t){this.camera=t,this.intensity=1,this.bias=0,this.normalBias=0,this.radius=1,this.blurSamples=8,this.mapSize=new Ht(512,512),this.map=null,this.mapPass=null,this.matrix=new ee,this.autoUpdate=!0,this.needsUpdate=!1,this._frustum=new qa,this._frameExtents=new Ht(1,1),this._viewportCount=1,this._viewports=[new te(0,0,1,1)]}getViewportCount(){return this._viewportCount}getFrustum(){return this._frustum}updateMatrices(t){const e=this.camera,n=this.matrix;al.setFromMatrixPosition(t.matrixWorld),e.position.copy(al),ol.setFromMatrixPosition(t.target.matrixWorld),e.lookAt(ol),e.updateMatrixWorld(),Hr.multiplyMatrices(e.projectionMatrix,e.matrixWorldInverse),this._frustum.setFromProjectionMatrix(Hr),n.set(.5,0,0,.5,0,.5,0,.5,0,0,.5,.5,0,0,0,1),n.multiply(Hr)}getViewport(t){return this._viewports[t]}getFrameExtents(){return this._frameExtents}dispose(){this.map&&this.map.dispose(),this.mapPass&&this.mapPass.dispose()}copy(t){return this.camera=t.camera.clone(),this.intensity=t.intensity,this.bias=t.bias,this.radius=t.radius,this.mapSize.copy(t.mapSize),this}clone(){return new this.constructor().copy(this)}toJSON(){const t={};return this.intensity!==1&&(t.intensity=this.intensity),this.bias!==0&&(t.bias=this.bias),this.normalBias!==0&&(t.normalBias=this.normalBias),this.radius!==1&&(t.radius=this.radius),(this.mapSize.x!==512||this.mapSize.y!==512)&&(t.mapSize=this.mapSize.toArray()),t.camera=this.camera.toJSON(!1).object,delete t.camera.matrix,t}}const ll=new ee,qi=new R,Gr=new R;class $m extends lc{constructor(){super(new Ve(90,1,.5,500)),this.isPointLightShadow=!0,this._frameExtents=new Ht(4,2),this._viewportCount=6,this._viewports=[new te(2,1,1,1),new te(0,1,1,1),new te(3,1,1,1),new te(1,1,1,1),new te(3,0,1,1),new te(1,0,1,1)],this._cubeDirections=[new R(1,0,0),new R(-1,0,0),new R(0,0,1),new R(0,0,-1),new R(0,1,0),new R(0,-1,0)],this._cubeUps=[new R(0,1,0),new R(0,1,0),new R(0,1,0),new R(0,1,0),new R(0,0,1),new R(0,0,-1)]}updateMatrices(t,e=0){const n=this.camera,s=this.matrix,r=t.distance||n.far;r!==n.far&&(n.far=r,n.updateProjectionMatrix()),qi.setFromMatrixPosition(t.matrixWorld),n.position.copy(qi),Gr.copy(n.position),Gr.add(this._cubeDirections[e]),n.up.copy(this._cubeUps[e]),n.lookAt(Gr),n.updateMatrixWorld(),s.makeTranslation(-qi.x,-qi.y,-qi.z),ll.multiplyMatrices(n.projectionMatrix,n.matrixWorldInverse),this._frustum.setFromProjectionMatrix(ll)}}class Jm extends rr{constructor(t,e,n=0,s=2){super(t,e),this.isPointLight=!0,this.type="PointLight",this.distance=n,this.decay=s,this.shadow=new $m}get power(){return this.intensity*4*Math.PI}set power(t){this.intensity=t/(4*Math.PI)}dispose(){this.shadow.dispose()}copy(t,e){return super.copy(t,e),this.distance=t.distance,this.decay=t.decay,this.shadow=t.shadow.clone(),this}}class Qm extends lc{constructor(){super(new ec(-5,5,5,-5,.5,500)),this.isDirectionalLightShadow=!0}}class t0 extends rr{constructor(t,e){super(t,e),this.isDirectionalLight=!0,this.type="DirectionalLight",this.position.copy(me.DEFAULT_UP),this.updateMatrix(),this.target=new me,this.shadow=new Qm}dispose(){this.shadow.dispose()}copy(t){return super.copy(t),this.target=t.target.clone(),this.shadow=t.shadow.clone(),this}}class cc extends rr{constructor(t,e){super(t,e),this.isAmbientLight=!0,this.type="AmbientLight"}}const cl=new ee;class e0{constructor(t,e,n=0,s=1/0){this.ray=new Xa(t,e),this.near=n,this.far=s,this.camera=null,this.layers=new Ya,this.params={Mesh:{},Line:{threshold:1},LOD:{},Points:{threshold:1},Sprite:{}}}set(t,e){this.ray.set(t,e)}setFromCamera(t,e){e.isPerspectiveCamera?(this.ray.origin.setFromMatrixPosition(e.matrixWorld),this.ray.direction.set(t.x,t.y,.5).unproject(e).sub(this.ray.origin).normalize(),this.camera=e):e.isOrthographicCamera?(this.ray.origin.set(t.x,t.y,(e.near+e.far)/(e.near-e.far)).unproject(e),this.ray.direction.set(0,0,-1).transformDirection(e.matrixWorld),this.camera=e):console.error("THREE.Raycaster: Unsupported camera type: "+e.type)}setFromXRController(t){return cl.identity().extractRotation(t.matrixWorld),this.ray.origin.setFromMatrixPosition(t.matrixWorld),this.ray.direction.set(0,0,-1).applyMatrix4(cl),this}intersectObject(t,e=!0,n=[]){return Ia(t,this,n,e),n.sort(hl),n}intersectObjects(t,e=!0,n=[]){for(let s=0,r=t.length;s<r;s++)Ia(t[s],this,n,e);return n.sort(hl),n}}function hl(i,t){return i.distance-t.distance}function Ia(i,t,e,n){let s=!0;if(i.layers.test(t.layers)&&i.raycast(t,e)===!1&&(s=!1),s===!0&&n===!0){const r=i.children;for(let a=0,o=r.length;a<o;a++)Ia(r[a],t,e,!0)}}typeof __THREE_DEVTOOLS__<"u"&&__THREE_DEVTOOLS__.dispatchEvent(new CustomEvent("register",{detail:{revision:Na}}));typeof window<"u"&&(window.__THREE__?console.warn("WARNING: Multiple instances of Three.js being imported."):window.__THREE__=Na);class n0{context=null;master=null;musicGain=null;musicTimer=null;musicStep=0;enabled;constructor(t){this.enabled=t}resume(){if(this.enabled){if(!this.context){const t=window.AudioContext||window.webkitAudioContext;if(!t){this.enabled=!1;return}this.context=new t,this.master=this.context.createGain(),this.master.gain.value=.35,this.master.connect(this.context.destination),this.musicGain=this.context.createGain(),this.musicGain.gain.value=.18,this.musicGain.connect(this.master)}this.context.state==="suspended"&&this.context.resume()}}tone(t,e,n={}){if(!this.enabled||!this.context||!this.master)return;const s=this.context.currentTime,r=this.context.createOscillator(),a=this.context.createGain();r.type=n.type||"sine",r.frequency.setValueAtTime(t,s),n.slideTo&&r.frequency.exponentialRampToValueAtTime(Math.max(20,n.slideTo),s+e),a.gain.setValueAtTime(1e-4,s),a.gain.exponentialRampToValueAtTime(n.gain??.25,s+.01),a.gain.exponentialRampToValueAtTime(1e-4,s+e),r.connect(a),a.connect(n.target??this.master),r.start(s),r.stop(s+e+.02)}noise(t,e=.2,n=900){if(!this.enabled||!this.context||!this.master)return;const s=this.context.currentTime,r=Math.max(1,Math.floor(this.context.sampleRate*t)),a=this.context.createBuffer(1,r,this.context.sampleRate),o=a.getChannelData(0);for(let c=0;c<r;c+=1)o[c]=(Math.random()*2-1)*(1-c/r);const l=this.context.createBufferSource();l.buffer=a;const h=this.context.createBiquadFilter();h.type="lowpass",h.frequency.value=n;const d=this.context.createGain();d.gain.value=e,l.connect(h),h.connect(d),d.connect(this.master),l.start(s)}chime(t){const e=t==="coffee"?520:t==="supply"?380:660;this.tone(e,.16,{type:"triangle",gain:.18}),window.setTimeout(()=>this.tone(e*1.5,.22,{type:"sine",gain:.16}),90)}footstep(t){this.noise(.09,t?.14:.09,t?1200:800)}laser(){this.tone(1200,.12,{type:"square",gain:.12,slideTo:240})}explosion(){this.noise(.5,.28,420),this.tone(90,.4,{type:"sawtooth",gain:.14,slideTo:40})}alarm(){this.tone(680,.5,{type:"square",gain:.1,slideTo:420})}warp(){this.tone(120,1.6,{type:"sawtooth",gain:.16,slideTo:1400}),this.noise(1.4,.16,2600)}playMusic(t){if(this.resume(),!this.enabled||!this.context||!this.musicGain)return;this.stopMusic(),this.musicStep=0;const e=320;this.musicTimer=window.setInterval(()=>{if(!this.context||!this.musicGain)return;const n=t[this.musicStep%t.length],s=this.musicStep%8<4?1:.5;this.tone(n*s,.32,{type:"triangle",gain:.22,target:this.musicGain}),this.musicStep%4===0&&this.tone(n*.5,.5,{type:"sine",gain:.3,target:this.musicGain}),this.musicStep+=1},e)}stopMusic(){this.musicTimer!==null&&(window.clearInterval(this.musicTimer),this.musicTimer=null)}dispose(){this.stopMusic(),this.context&&this.context.close(),this.context=null,this.master=null,this.musicGain=null}}const Ji=.42,i0=1.78,s0=1.15,r0=1.62,a0=1;class o0{boxes=[];add(t,e,n){this.boxes.push({min:t,max:e,tag:n})}addBox(t){this.boxes.push(t)}addFromCenter(t,e,n){const s=e.clone().multiplyScalar(.5);this.boxes.push({min:t.clone().sub(s),max:t.clone().add(s),tag:n})}query(t,e=[]){e.length=0;for(const n of this.boxes)n.max.x<=t.min.x||n.min.x>=t.max.x||n.max.y<=t.min.y||n.min.y>=t.max.y||n.max.z<=t.min.z||n.min.z>=t.max.z||e.push(n);return e}}const l0=[];function Ki(i,t,e,n,s){if(s===0)return{value:t[n],blocked:!1};const r=t[n];t[n]=r+s;const a=Ji,o=t.y,l=t.y+e,h={min:new R(t.x-a,o,t.z-a),max:new R(t.x+a,l,t.z+a)},d=i.query(h,l0);if(d.length===0)return{value:t[n],blocked:!1};let c=t[n];for(const u of d)n==="y"?s>0?c=Math.min(c,u.min.y-e-1e-4):c=Math.max(c,u.max.y+1e-4):n==="x"?s>0?c=Math.min(c,u.min.x-a-1e-4):c=Math.max(c,u.max.x+a+1e-4):s>0?c=Math.min(c,u.min.z-a-1e-4):c=Math.max(c,u.max.z+a+1e-4);return t[n]=c,{value:c,blocked:!0}}function c0(i,t,e,n){const s={position:t.clone(),grounded:!1,hitCeiling:!1,collidedX:!1,collidedZ:!1},r=t.clone(),a=.55;let o=r.y;const l=Ki(i,r,e,"x",n.x);s.collidedX=l.blocked;const h=Ki(i,r,e,"z",n.z);if(s.collidedZ=h.blocked,s.collidedX||s.collidedZ){const f=r.clone();f.y=t.y+a;const g=Ki(i,f,e,"x",n.x),v=Ki(i,f,e,"z",n.z);!g.blocked&&!v.blocked&&(r.x=f.x,r.z=f.z,r.y=t.y,s.collidedX=!1,s.collidedZ=!1)}const d={min:new R(r.x-Ji,r.y-.12,r.z-Ji),max:new R(r.x+Ji,r.y-.001,r.z+Ji)},c=i.query(d,[]),u=c.length>0;if(n.y<=0&&u&&r.y+n.y<t.y){const f=c.reduce((g,v)=>Math.max(g,v.max.y),-1/0);r.y=f+1e-4,s.grounded=!0}else Ki(i,r,e,"y",n.y).blocked&&(n.y<0?s.grounded=!0:s.hitCeiling=!0);return o=r.y,s.position.copy(r),s.position.y=o,s}class h0{root;crosshair;prompt;status;toasts;banner;minigame;dialog=null;dialogResolve=null;constructor(t){this.root=t,t.innerHTML="",this.crosshair=document.createElement("div"),this.crosshair.className="hud-crosshair",this.crosshair.innerHTML="<span></span><span></span>",this.prompt=document.createElement("div"),this.prompt.className="hud-prompt hidden",this.status=document.createElement("div"),this.status.className="hud-status hidden",this.toasts=document.createElement("div"),this.toasts.className="hud-toasts",this.banner=document.createElement("div"),this.banner.className="hud-banner hidden",this.minigame=document.createElement("div"),this.minigame.className="hud-minigame hidden",t.append(this.crosshair,this.prompt,this.status,this.banner,this.minigame,this.toasts)}setCrosshairVisible(t,e="dot"){this.crosshair.classList.toggle("hidden",!t),this.crosshair.classList.toggle("pointer",e==="pointer")}showPrompt(t,e="E"){if(!t){this.prompt.classList.add("hidden");return}this.prompt.classList.remove("hidden"),this.prompt.innerHTML="<kbd>"+e+"</kbd><span>"+Ke(t)+"</span>"}setStatus(t){if(!t||t.length===0){this.status.classList.add("hidden");return}this.status.classList.remove("hidden"),this.status.innerHTML=t.map(e=>"<div>"+Ke(e)+"</div>").join("")}setBanner(t,e="warn"){if(!t){this.banner.classList.add("hidden");return}this.banner.classList.remove("hidden"),this.banner.classList.toggle("warn",e==="warn"),this.banner.textContent=t}setMinigame(t){if(!t){this.minigame.classList.add("hidden");return}this.minigame.classList.remove("hidden"),this.minigame.innerHTML='<div class="mg-title">'+Ke(t.title)+'</div><div class="mg-score">'+Ke(t.score)+"</div>"+(t.extra?'<div class="mg-extra">'+Ke(t.extra)+"</div>":"")+(t.hint?'<div class="mg-hint">'+Ke(t.hint)+"</div>":"")}toast(t,e="info",n=3600){const s=document.createElement("div");s.className="hud-toast "+e,s.textContent=t,this.toasts.appendChild(s),window.setTimeout(()=>{s.classList.add("leaving"),window.setTimeout(()=>s.remove(),400)},n)}confirm(t){return new Promise(e=>{const n=document.createElement("div");n.className="hud-dialog-overlay",n.innerHTML='<div class="hud-dialog'+(t.danger?" danger":"")+'"><h3>'+Ke(t.title)+"</h3>"+(t.body?"<p>"+Ke(t.body)+"</p>":"")+'<div class="hud-dialog-actions"><button class="ghost" data-action="cancel">'+Ke(t.cancelLabel||"取消")+'</button><button class="'+(t.danger?"danger":"primary")+'" data-action="ok">'+Ke(t.confirmLabel||"确认")+"</button></div></div>";const s=a=>{n.remove(),window.removeEventListener("keydown",r,!0),e(a)},r=a=>{a.key==="Escape"?(a.stopPropagation(),s(!1)):a.key==="Enter"&&(a.stopPropagation(),s(!0))};n.addEventListener("click",a=>{const o=a.target,l=o.dataset.action;l==="ok"?s(!0):(l==="cancel"||o===n)&&s(!1)}),window.addEventListener("keydown",r,!0),document.body.appendChild(n)})}ask(t){return this.dialog&&this.dialogResolve?.(null),new Promise(e=>{const n=document.createElement("div");n.className="hud-dialog-overlay",n.innerHTML='<div class="hud-dialog"><h3>'+Ke(t.title)+"</h3>"+(t.hint?"<p>"+Ke(t.hint)+"</p>":"")+'<input type="text" /><div class="hud-dialog-actions"><button class="ghost" data-action="cancel">取消</button><button class="primary" data-action="ok">确定</button></div></div>';const s=n.querySelector("input");s.placeholder=t.placeholder||"",s.value=t.value||"",this.dialog=n,this.dialogResolve=e;const r=a=>{n.remove(),this.dialog=null,this.dialogResolve=null,e(a)};n.addEventListener("click",a=>{const o=a.target;o.dataset.action==="ok"?r(s.value):(o.dataset.action==="cancel"||o===n)&&r(null)}),s.addEventListener("keydown",a=>{a.stopPropagation(),a.key==="Enter"&&r(s.value),a.key==="Escape"&&r(null)}),document.body.appendChild(n),s.focus(),s.select()})}}function Ke(i){return String(i).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;")}const ul={ArrowUp:"up",ArrowDown:"down",ArrowLeft:"left",ArrowRight:"right"," ":"space"};class u0{keys=new Set;pointer={x:0,y:0,clientX:0,clientY:0,down:!1,clicked:!1,deltaX:0,deltaY:0,wheel:0};pressedThisFrame=new Set;pressedQueue=[];mode="world";locked=!1;textMode=!1;sensitivity=1;invertY=!1;element;listeners=[];onClickHandlers=[];constructor(t){this.element=t,this.bind()}on(t,e,n,s){t.addEventListener(e,n,s),this.listeners.push(()=>t.removeEventListener(e,n,s))}bind(){this.on(window,"keydown",t=>{if(this.textMode)return;const e=this.normalize(t);t.repeat||(this.keys.has(e)||this.pressedQueue.push(e),this.keys.add(e),(e==="space"||e==="tab")&&t.preventDefault())}),this.on(window,"keyup",t=>{this.keys.delete(this.normalize(t))}),this.on(window,"blur",()=>{this.keys.clear()}),this.on(document,"mousemove",t=>{this.locked&&(this.pointer.deltaX+=t.movementX||0,this.pointer.deltaY+=t.movementY||0),this.pointer.clientX=t.clientX,this.pointer.clientY=t.clientY;const e=this.element.getBoundingClientRect();this.pointer.x=(t.clientX-e.left)/e.width*2-1,this.pointer.y=-((t.clientY-e.top)/e.height)*2+1}),this.on(this.element,"mousedown",t=>{t.button===0&&(this.pointer.down=!0)}),this.on(window,"mouseup",t=>{if(t.button===0){if(this.pointer.down){this.pointer.clicked=!0;for(const e of this.onClickHandlers)e()}this.pointer.down=!1}}),this.on(window,"wheel",t=>{this.pointer.wheel+=t.deltaY},{passive:!0}),this.on(document,"pointerlockchange",()=>{this.locked=document.pointerLockElement===this.element,!this.locked&&this.mode==="world"&&this.onLockLost?.()})}normalize(t){return ul[t.key]?ul[t.key]:t.key==="Shift"?"shift":t.key==="Control"?"control":t.key==="Escape"?"escape":t.key==="Tab"?"tab":t.key.length===1?t.key.toLowerCase():t.key}onLockLost=null;onNextClick(t){return this.onClickHandlers.push(t),()=>{const e=this.onClickHandlers.indexOf(t);e>=0&&this.onClickHandlers.splice(e,1)}}requestLock(){if(this.locked)return;const t=this.element.requestPointerLock?.bind(this.element);if(t){const e=t();e&&typeof e.catch=="function"&&e.catch(()=>{})}}releaseLock(){document.pointerLockElement===this.element&&document.exitPointerLock()}isDown(t){return this.keys.has(t)}wasPressed(t){const e=this.pressedQueue.indexOf(t);return e<0?!1:(this.pressedQueue.splice(e,1),!0)}peekPressed(t){return this.pressedQueue.includes(t)}endFrame(){this.pointer.clicked=!1,this.pointer.deltaX=0,this.pointer.deltaY=0,this.pointer.wheel=0,this.pressedQueue.length=0,this.pressedThisFrame.clear()}dispose(){for(const t of this.listeners)t();this.listeners.length=0,this.onClickHandlers.length=0}}const dl=4.6,d0=7.4,f0=2,p0=46,m0=9,g0=12,_0=26,fl=8.4,x0=3.4;class v0{constructor(t){this.ladders=t}position=new R(0,0,0);velocity=new R;yaw=0;pitch=0;grounded=!1;crouching=!1;sprinting=!1;inLadder=!1;bobPhase=0;stepTimer=0;focusBlend=0;eyeOffset=new R;get height(){return this.crouching?s0:i0}get eyeHeight(){return this.crouching?a0:r0}spawn(t,e){this.position.copy(t),this.velocity.set(0,0,0),this.yaw=e,this.pitch=0,this.grounded=!1,this.focusBlend=0}eyePosition(t=new R){const e=Math.sin(this.bobPhase*2)*.028*Math.min(1,this.speedRatio*2);return t.set(this.position.x,this.position.y+this.eyeHeight+e,this.position.z)}get speedRatio(){const t=Math.hypot(this.velocity.x,this.velocity.z);return Math.min(1,t/dl)}ladderAt(t){for(const e of this.ladders)if(t.x>e.min.x&&t.x<e.max.x&&t.z>e.min.z&&t.z<e.max.z&&t.y+this.height>e.min.y&&t.y<e.max.y)return!0;return!1}update(t,e,n,s){const r=s.enabled;if(r&&n.locked){const y=.0022*n.sensitivity;this.yaw-=n.pointer.deltaX*y,this.pitch-=n.pointer.deltaY*y*(n.invertY?-1:1);const _=Math.PI/2-.02;this.pitch=Math.max(-_,Math.min(_,this.pitch))}const a=new R(-Math.sin(this.yaw),0,-Math.cos(this.yaw)),o=new R(Math.cos(this.yaw),0,-Math.sin(this.yaw)),l=new R;r&&((n.isDown("w")||n.isDown("up"))&&l.add(a),(n.isDown("s")||n.isDown("down"))&&l.sub(a),(n.isDown("d")||n.isDown("right"))&&l.add(o),(n.isDown("a")||n.isDown("left"))&&l.sub(o)),l.lengthSq()>0&&l.normalize(),this.crouching=r&&n.isDown("shift");const h=r&&!this.crouching&&n.isDown("control");this.sprinting=h&&l.lengthSq()>0;const d=Math.max(.2,s.speedScale??1),c=(this.crouching?f0:this.sprinting?d0:dl)*d,u=this.grounded?p0:m0,f=l.multiplyScalar(c);if(this.velocity.x=Fs(this.velocity.x,f.x,u*t),this.velocity.z=Fs(this.velocity.z,f.z,u*t),this.grounded&&l.lengthSq()===0){const y=g0*t;this.velocity.x=Fs(this.velocity.x,0,y*Math.abs(this.velocity.x)+y),this.velocity.z=Fs(this.velocity.z,0,y*Math.abs(this.velocity.z)+y)}if(this.inLadder=this.ladderAt(this.position),this.inLadder){const y=(r&&(n.isDown("w")||n.isDown("up"))?1:0)-(r&&(n.isDown("s")||n.isDown("down"))?1:0);this.velocity.y=y*x0,r&&n.isDown("space")&&(this.velocity.y=fl*.6)}else this.velocity.y-=_0*t,this.velocity.y<-60&&(this.velocity.y=-60),r&&this.grounded&&n.isDown("space")&&(this.velocity.y=fl*Math.max(.5,s.jumpScale??1),this.grounded=!1);const g=this.velocity.clone().multiplyScalar(t),v=this.position.clone(),m=c0(e,this.position,this.height,g);this.position.copy(m.position),m.grounded?(this.velocity.y<0&&(this.velocity.y=0),this.grounded=!0):this.grounded=!1,m.hitCeiling&&this.velocity.y>0&&(this.velocity.y=0),m.collidedX&&(this.velocity.x=0),m.collidedZ&&(this.velocity.z=0);const p=Math.hypot(this.position.x-v.x,this.position.z-v.z)/Math.max(t,1e-4);this.grounded&&p>.6?(this.bobPhase+=t*p*1.5,this.stepTimer-=t*p,this.stepTimer<=0&&(this.stepTimer=2.2,s.onStep?.(this.sprinting))):this.bobPhase+=t*.6}}function Fs(i,t,e){return i<t?Math.min(i+e,t):i>t?Math.max(i-e,t):i}const M0="neobot-dashboard-token",y0="neobot-dashboard-csrf";function S0(){try{return localStorage.getItem(M0)||""}catch{return""}}function w0(){try{return localStorage.getItem(y0)||""}catch{return""}}async function Qs(i,t,e={}){const n=new Headers(e.headers||{}),s=S0();s&&n.set("X-Token",s);const r=(e.method||"GET").toUpperCase();if(r!=="GET"&&r!=="HEAD"){const a=w0();a&&n.set("X-CSRF-Token",a),n.set("Content-Type","application/json")}try{const a=await fetch(i+t,{...e,headers:n,cache:"no-store"}),o=await a.json().catch(()=>null);return a.status===401?{ok:!1,data:null,error:"需要登录网页面板",status:401}:a.ok?{ok:!0,data:o,error:null,status:a.status}:{ok:!1,data:o,error:o&&o.error||"HTTP "+a.status,status:a.status}}catch(a){return{ok:!1,data:null,error:a.message||"网络错误",status:0}}}const E0={base:ks,get(i){return Qs(ks(),i)},post(i,t){return Qs(ks(),i,{method:"POST",body:t===void 0?void 0:JSON.stringify(t)})}},Mi={base:ur,get(i){return Qs(ur(),i)},post(i,t){return Qs(ur(),i,{method:"POST",body:t===void 0?void 0:JSON.stringify(t)})}};class re{constructor(t,e,n,s){this.loader=t,this.intervalMs=e,this.onData=n,this.onError=s}timer=null;busy=!1;stopped=!0;start(t=!0){this.stopped&&(this.stopped=!1,t&&this.tick(),this.timer=window.setInterval(()=>void this.tick(),this.intervalMs))}stop(){this.stopped=!0,this.timer!==null&&(window.clearInterval(this.timer),this.timer=null)}get running(){return!this.stopped}async tick(){if(!(this.stopped||this.busy)){this.busy=!0;try{const t=await this.loader();!this.stopped&&t.ok&&t.data?this.onData(t.data):!t.ok&&this.onError&&t.status!==401&&this.onError(t.error||"请求失败")}finally{this.busy=!1}}}}const pl=8e3,b0=["varying vec3 vDir;","void main() {","  vDir = normalize(position);","  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);","}"].join(`
`),T0=["varying vec3 vDir;","uniform float uTime;","uniform vec3 uNebulaA;","uniform vec3 uNebulaB;","uniform float uSeed;","float hash13(vec3 p) {","  p = fract(p * 0.1031);","  p += dot(p, p.yzx + 33.33);","  return fract((p.x + p.y) * p.z);","}","float noise(vec3 p) {","  vec3 i = floor(p);","  vec3 f = fract(p);","  f = f * f * (3.0 - 2.0 * f);","  float n000 = hash13(i);","  float n100 = hash13(i + vec3(1.0, 0.0, 0.0));","  float n010 = hash13(i + vec3(0.0, 1.0, 0.0));","  float n110 = hash13(i + vec3(1.0, 1.0, 0.0));","  float n001 = hash13(i + vec3(0.0, 0.0, 1.0));","  float n101 = hash13(i + vec3(1.0, 0.0, 1.0));","  float n011 = hash13(i + vec3(0.0, 1.0, 1.0));","  float n111 = hash13(i + vec3(1.0, 1.0, 1.0));","  return mix(mix(mix(n000, n100, f.x), mix(n010, n110, f.x), f.y),","             mix(mix(n001, n101, f.x), mix(n011, n111, f.x), f.y), f.z);","}","float fbm(vec3 p) {","  float value = 0.0;","  float amplitude = 0.5;","  for (int i = 0; i < 4; i++) {","    value += amplitude * noise(p);","    p *= 2.02;","    amplitude *= 0.5;","  }","  return value;","}","float starLayer(vec3 dir, float scale, float threshold) {","  vec3 p = dir * scale;","  vec3 cell = floor(p);","  vec3 local = fract(p) - 0.5;","  float h = hash13(cell + uSeed);","  float present = step(threshold, h);","  float core = smoothstep(0.16, 0.0, length(local));","  float twinkle = 0.75 + 0.25 * sin(uTime * 1.7 + h * 60.0);","  return present * core * twinkle;","}","void main() {","  vec3 dir = normalize(vDir);","  vec3 base = vec3(0.004, 0.008, 0.016);","  float nebula = fbm(dir * 2.4 + uSeed);","  float nebula2 = fbm(dir * 5.1 - uSeed * 0.6);","  vec3 color = base;","  color += uNebulaA * pow(smoothstep(0.45, 0.95, nebula), 2.2) * 0.9;","  color += uNebulaB * pow(smoothstep(0.5, 1.0, nebula2), 3.0) * 0.55;","  float stars = starLayer(dir, 420.0, 0.9955) * 1.5;","  stars += starLayer(dir, 260.0, 0.9975) * 2.2;","  stars += starLayer(dir, 150.0, 0.9990) * 3.4;","  color += vec3(0.85, 0.92, 1.0) * stars;","  gl_FragColor = vec4(color, 1.0);","}"].join(`
`),A0=["varying vec3 vNormal;","varying vec3 vPosition;","varying vec3 vWorld;","void main() {","  vNormal = normalize(normalMatrix * normal);","  vPosition = position;","  vWorld = (modelMatrix * vec4(position, 1.0)).xyz;","  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);","}"].join(`
`),R0=["varying vec3 vNormal;","varying vec3 vPosition;","varying vec3 vWorld;","uniform vec3 uColorA;","uniform vec3 uColorB;","uniform vec3 uSun;","uniform vec3 uAtmosphere;","float hash13(vec3 p) {","  p = fract(p * 0.1031);","  p += dot(p, p.yzx + 33.33);","  return fract((p.x + p.y) * p.z);","}","float noise(vec3 p) {","  vec3 i = floor(p);","  vec3 f = fract(p);","  f = f * f * (3.0 - 2.0 * f);","  float n000 = hash13(i);","  float n100 = hash13(i + vec3(1.0, 0.0, 0.0));","  float n010 = hash13(i + vec3(0.0, 1.0, 0.0));","  float n110 = hash13(i + vec3(1.0, 1.0, 0.0));","  float n001 = hash13(i + vec3(0.0, 0.0, 1.0));","  float n101 = hash13(i + vec3(1.0, 0.0, 1.0));","  float n011 = hash13(i + vec3(0.0, 1.0, 1.0));","  float n111 = hash13(i + vec3(1.0, 1.0, 1.0));","  return mix(mix(mix(n000, n100, f.x), mix(n010, n110, f.x), f.y),","             mix(mix(n001, n101, f.x), mix(n011, n111, f.x), f.y), f.z);","}","void main() {","  vec3 dir = normalize(vPosition);","  float bands = noise(dir * 4.0) * 0.6 + noise(dir * 12.0) * 0.4;","  vec3 surface = mix(uColorA, uColorB, smoothstep(0.35, 0.7, bands));","  float lambert = clamp(dot(normalize(vNormal), normalize(uSun)), 0.0, 1.0);","  float terminator = smoothstep(0.0, 0.35, lambert);","  vec3 lit = surface * (0.12 + terminator * 1.25);","  vec3 viewDir = normalize(cameraPosition - vWorld);","  float fresnel = pow(1.0 - clamp(dot(viewDir, normalize(vNormal)), 0.0, 1.0), 3.0);","  vec3 atmosphere = uAtmosphere * fresnel * (0.25 + terminator * 0.9);","  gl_FragColor = vec4(lit + atmosphere, 1.0);","}"].join(`
`),C0=["varying vec2 vUv;","void main() {","  vUv = uv;","  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);","}"].join(`
`),P0=["varying vec2 vUv;","uniform float uWarp;","uniform float uTime;","uniform vec3 uColor;","float hash21(vec2 p) {","  p = fract(p * vec2(123.34, 456.21));","  p += dot(p, p + 45.32);","  return fract(p.x * p.y);","}","void main() {","  if (uWarp <= 0.001) discard;","  vec2 centered = vUv - 0.5;","  float radius = length(centered);","  float angle = atan(centered.y, centered.x);","  float streaks = 0.0;","  for (int i = 0; i < 3; i++) {","    float layer = float(i);","    float a = floor((angle + layer * 1.7) * 24.0) / 24.0;","    float h = hash21(vec2(a, layer));","    float speed = 1.6 + h * 2.4;","    float phase = fract(radius * (2.0 + h * 3.0) - uTime * speed);","    streaks += smoothstep(0.85, 1.0, phase) * (0.4 + 0.6 * h);","  }","  float falloff = smoothstep(0.05, 0.42, radius);","  float alpha = streaks * falloff * uWarp;","  gl_FragColor = vec4(uColor * (0.6 + streaks), clamp(alpha, 0.0, 0.95));","}"].join(`
`);class ml{constructor(t,e,n){this.scene=t,this.camera=e,this.quality=n.quality,this.seed=n.seed??Math.random()*1e3,this.skyMaterial=new an({vertexShader:b0,fragmentShader:T0,side:Pe,depthWrite:!1,uniforms:{uTime:{value:0},uSeed:{value:this.seed},uNebulaA:{value:new Pt(2772904)},uNebulaB:{value:new Pt(10108848)}}}),this.sky=new Ct(new Pn(pl,32,16),this.skyMaterial),this.sky.name="space-sky",this.sky.frustumCulled=!1,t.add(this.sky),this.planetMaterial=new an({vertexShader:A0,fragmentShader:R0,uniforms:{uColorA:{value:new Pt(1920890)},uColorB:{value:new Pt(8833192)},uSun:{value:new R(1,.3,.2).normalize()},uAtmosphere:{value:new Pt(6203647)}}}),this.planet=new Ct(new Pn(420,48,32),this.planetMaterial),this.planet.position.set(1400,-260,-900),t.add(this.planet),this.moon=new Ct(new Pn(90,24,16),new Me({color:10134189,roughness:.95,metalness:.05})),this.moon.position.set(900,180,1200),t.add(this.moon),this.sunLight=new t0(16773853,2.1),this.sunLight.position.set(1,.3,.2).multiplyScalar(2e3),t.add(this.sunLight),this.ambient=new cc(3096661,.75),t.add(this.ambient);const s=new fe({color:16773312});this.sun=new Ct(new Pn(60,20,12),s),this.sun.position.copy(this.sunLight.position),t.add(this.sun),this.sunGlow=new Ct(new Pn(170,20,12),new fe({color:16767392,transparent:!0,opacity:.18,blending:Ai,depthWrite:!1})),this.sunGlow.position.copy(this.sun.position),t.add(this.sunGlow),this.asteroids=this.createAsteroidField(),t.add(this.asteroids),this.createTraffic(),this.warpMaterial=new an({vertexShader:C0,fragmentShader:P0,transparent:!0,depthTest:!1,depthWrite:!1,blending:Ai,uniforms:{uWarp:{value:0},uTime:{value:0},uColor:{value:new Pt(10479871)}}}),this.warpOverlay=new Ct(new Qn(2,2),this.warpMaterial),this.warpOverlay.position.set(0,0,-1),this.warpOverlay.frustumCulled=!1,this.warpOverlay.renderOrder=999,e.add(this.warpOverlay),t.add(e),t.fog=new ja(329485,this.quality.fogDensity)}sky;skyMaterial;planet;planetMaterial;moon;sun;sunGlow;asteroids;asteroidData=[];traffic=[];warpOverlay;warpMaterial;sunLight;ambient;quality;dummy=new me;seed;warpState="idle";warpTimer=0;warpAmount=0;onArrive=null;elapsed=0;createAsteroidField(){const t=new cs(1,1),e=t.attributes.position;for(let r=0;r<e.count;r+=1){const a=.7+Math.random()*.6;e.setXYZ(r,e.getX(r)*a,e.getY(r)*a*(.75+Math.random()*.5),e.getZ(r)*a)}t.computeVertexNormals();const n=new Me({color:9077624,roughness:.95,metalness:.08,flatShading:!0}),s=new qm(t,n,this.quality.asteroidCount);s.instanceMatrix.setUsage(uh),s.frustumCulled=!1;for(let r=0;r<this.quality.asteroidCount;r+=1)this.asteroidData.push(this.spawnAsteroid(!0));return s}spawnAsteroid(t=!1){const e=Math.random()*Math.PI*2,n=t?200+Math.random()*1400:1200+Math.random()*900,s=(Math.random()-.5)*700,r=4+Math.random()*46,a=4+Math.random()*22,o=new R(Math.cos(e)*Math.random()-.2,(Math.random()-.5)*.1,Math.sin(e)*Math.random()).normalize();return{position:new R(Math.cos(e)*n,s,Math.sin(e)*n*.6),velocity:o.multiplyScalar(a),rotation:new on(Math.random()*3,Math.random()*3,Math.random()*3),spin:new R((Math.random()-.5)*.6,(Math.random()-.5)*.6,(Math.random()-.5)*.6),scale:r}}createTraffic(){const t=[10466504,13153439,9414840,12101832];for(let e=0;e<this.quality.trafficCount;e+=1){const n=new Ze,s=t[e%t.length],r=new Ct(new Te(26,7,9),new Me({color:s,roughness:.5,metalness:.7})),a=new Ct(new Te(8,4,6),new Me({color:14344166,roughness:.4,metalness:.8}));a.position.x=16;const o=new Ct(new Te(10,9,1.4),new Me({color:8227740,roughness:.6,metalness:.5}));o.position.set(-4,6,0);const l=new Ct(new Jn(1.6,2.4,3,12),new fe({color:8378623}));l.rotation.z=Math.PI/2,l.position.x=-15,n.add(r,a,o,l),this.resetTraffic(n),this.scene.add(n),this.traffic.push({root:n,velocity:new R,life:0})}}resetTraffic(t){const e=Math.random()*Math.PI*2,n=400+Math.random()*900;t.position.set(Math.cos(e)*n,(Math.random()-.5)*260,Math.sin(e)*n);const s=new R((Math.random()-.5)*600,(Math.random()-.5)*200,(Math.random()-.5)*600),r=this.traffic.find(l=>l.root===t),a=22+Math.random()*40,o=s.clone().sub(t.position).normalize().multiplyScalar(a);r&&r.velocity.copy(o),t.lookAt(t.position.clone().add(o))}triggerWarp(t){return this.warpState!=="idle"?!1:(this.warpState="charging",this.warpTimer=0,this.onArrive=t??null,!0)}get warping(){return this.warpState!=="idle"}get warpPhase(){return this.warpState}get nebulaColors(){const t=this.skyMaterial.uniforms.uNebulaA.value,e=this.skyMaterial.uniforms.uNebulaB.value;return[t.getHex(),e.getHex()]}reroll(){this.seed=Math.random()*1e3,this.skyMaterial.uniforms.uSeed.value=this.seed;const t=[[2772904,10108848,1920890,8833192,6203647],[11026255,14191167,8010269,13150342,16754782],[2795631,4165592,1931861,8833224,6225864],[7285416,14172047,3808634,11044552,11034367],[11051050,14179903,8024861,13156486,16770142]],e=t[Math.floor(Math.random()*t.length)];this.skyMaterial.uniforms.uNebulaA.value.setHex(e[0]),this.skyMaterial.uniforms.uNebulaB.value.setHex(e[1]),this.planetMaterial.uniforms.uColorA.value.setHex(e[2]),this.planetMaterial.uniforms.uColorB.value.setHex(e[3]),this.planetMaterial.uniforms.uAtmosphere.value.setHex(e[4]);const n=Math.random()*Math.PI*2,s=1200+Math.random()*900;this.planet.position.set(Math.cos(n)*s,-200-Math.random()*300,Math.sin(n)*s);const r=Math.random()*Math.PI*2;this.sunLight.position.set(Math.cos(r)*2e3,200+Math.random()*900,Math.sin(r)*2e3),this.sun.position.copy(this.sunLight.position),this.sunGlow.position.copy(this.sunLight.position),this.planetMaterial.uniforms.uSun.value.copy(this.sunLight.position).normalize();for(const a of this.asteroidData)Object.assign(a,this.spawnAsteroid(!0));for(const a of this.traffic)this.resetTraffic(a.root)}update(t){this.elapsed+=t,this.skyMaterial.uniforms.uTime.value=this.elapsed,this.sky.position.copy(this.camera.position),this.sun.position.copy(this.camera.position).add(this.sunLight.position.clone().normalize().multiplyScalar(pl*.55)),this.sunGlow.position.copy(this.sun.position),this.planet.rotation.y+=t*.01,this.moon.rotation.y+=t*.02;for(let e=0;e<this.asteroidData.length;e+=1){const n=this.asteroidData[e];if(n.position.addScaledVector(n.velocity,t),n.rotation.x+=n.spin.x*t,n.rotation.y+=n.spin.y*t,n.rotation.z+=n.spin.z*t,n.position.length()>2600){const s=this.spawnAsteroid(!1);Object.assign(n,s)}this.dummy.position.copy(n.position),this.dummy.rotation.copy(n.rotation),this.dummy.scale.setScalar(n.scale),this.dummy.updateMatrix(),this.asteroids.setMatrixAt(e,this.dummy.matrix)}this.asteroids.instanceMatrix.needsUpdate=!0;for(const e of this.traffic)e.root.position.addScaledVector(e.velocity,t),e.life+=t,(e.life>90||e.root.position.length()>2400)&&(this.resetTraffic(e.root),e.life=0);this.warpState!=="idle"?(this.warpTimer+=t,this.warpState==="charging"?(this.warpAmount=Math.min(.35,this.warpTimer*.35),this.warpTimer>1.1&&(this.warpState="jumping",this.warpTimer=0)):this.warpState==="jumping"?(this.warpAmount=Math.min(1,.35+this.warpTimer*.75),this.warpTimer>2.4&&(this.warpState="arriving",this.warpTimer=0,this.reroll(),this.onArrive?.(),this.onArrive=null)):(this.warpAmount=Math.max(0,1-this.warpTimer*1.2),this.warpTimer>1.1&&(this.warpState="idle",this.warpAmount=0)),this.warpMaterial.uniforms.uWarp.value=this.warpAmount,this.warpMaterial.uniforms.uTime.value=this.elapsed):this.warpAmount>0&&(this.warpMaterial.uniforms.uWarp.value=this.warpAmount)}dispose(){this.scene.remove(this.ambient),this.scene.remove(this.sunLight),this.scene.remove(this.sky),this.scene.remove(this.planet),this.scene.remove(this.moon),this.scene.remove(this.sun),this.scene.remove(this.sunGlow),this.scene.remove(this.asteroids);for(const t of this.traffic)this.scene.remove(t.root);this.camera.remove(this.warpOverlay),this.scene.fog=null}}const L0={standby:!1,power_state:"unknown",power_available:!1,reason:null,operator:null,since_text:null,standby_seconds:null,online:!1,plugins:{total:0,running:0,error:0},uptime_seconds:0};class D0{status={...L0};manageEnabled=!0;playerName="舰长";quality="medium";listeners=new Set;subscribe(t){return this.listeners.add(t),()=>this.listeners.delete(t)}update(t){this.status={...this.status,...t},this.emit()}setManageEnabled(t){this.manageEnabled!==t&&(this.manageEnabled=t,this.emit())}emit(){for(const t of this.listeners)t()}availability(t){const e={usage:{reason:"待机中：模型调用统计已停止采集",hint:"在主控台点击「恢复运行」后重新上线"},analysis:{reason:"待机中：Agent 运行时未启动",hint:"在主控台点击「恢复运行」后重新上线"},bots:{reason:"待机中：OneBot 连接已断开",hint:"在主控台点击「恢复运行」后重新上线"}};if(this.status.standby){const n=e[t];return n?{available:!1,reason:n.reason,hint:n.hint,readOnly:!0}:{available:!0,reason:"舰船处于低功耗待机状态",hint:"",readOnly:!1}}return t==="bots"&&!this.status.online?{available:!0,reason:"未检测到 OneBot 连接：数据可能不是最新的",hint:"确认 NapCat / OneBot 是否已启动",readOnly:!1}:(t==="plugins"||t==="config")&&!this.manageEnabled?{available:!0,reason:"当前会话为只读模式（manage_plugins=false 或远程管理已关闭）",hint:"在面板「配置管理 → dashboard」中开启管理功能",readOnly:!0}:{available:!0,reason:"",hint:"",readOnly:!1}}}class I0{element;active=!1;value="";onCommit=null;onCancel=null;onType=null;constructor(){const t=document.createElement("input");t.type="text",t.autocomplete="off",t.autocapitalize="off",t.spellcheck=!1,t.setAttribute("aria-hidden","true"),t.className="text-capture",document.body.appendChild(t),this.element=t,t.addEventListener("input",()=>{this.value=t.value,this.onType?.(this.value)}),t.addEventListener("keydown",e=>{if(e.stopPropagation(),e.key==="Enter"){e.preventDefault();const n=this.value;this.close(),this.onCommit?.(n)}else e.key==="Escape"&&(e.preventDefault(),this.close(),this.onCancel?.())}),t.addEventListener("blur",()=>{this.active&&(this.active=!1,this.onCancel?.())})}get isActive(){return this.active}open(t){this.value=t.initial??"",this.element.value=this.value,this.onCommit=t.onCommit,this.onCancel=t.onCancel??null,this.onType=t.onType??null,this.active=!0,this.element.focus({preventScroll:!0}),this.element.setSelectionRange(this.value.length,this.value.length)}close(){this.active=!1,this.onCommit=null,this.onCancel=null,this.onType=null,this.element.blur()}}function Ua(i,t,e=256){const n=document.createElement("canvas");n.width=e,n.height=e;const s=n.getContext("2d");s.fillStyle=i,s.fillRect(0,0,e,e),s.strokeStyle=t,s.lineWidth=2;const r=e/4;for(let o=0;o<=4;o+=1)s.beginPath(),s.moveTo(o*r,0),s.lineTo(o*r,e),s.stroke(),s.beginPath(),s.moveTo(0,o*r),s.lineTo(e,o*r),s.stroke();s.fillStyle="rgba(255,255,255,0.05)";for(let o=0;o<60;o+=1)s.fillRect(Math.random()*e,Math.random()*e,2,2);const a=new Za(n);return a.wrapS=ss,a.wrapT=ss,a.anisotropy=4,a}function U0(i,t,e=256){const n=Ua(i,t,e);return n.repeat.set(2,2),n}function N0(){const i=Ua("#2b323d","#39414f");i.repeat.set(2,1);const t=U0("#1d2229","#2c333d"),e=Ua("#191d24","#242a33");return{hull:new Me({color:5923699,metalness:.85,roughness:.42,side:hn}),wall:new Me({map:i,color:12898269,metalness:.3,roughness:.68,side:de,emissive:new Pt(857632),emissiveIntensity:1}),wallAccent:new Me({color:3108236,metalness:.5,roughness:.4,emissive:new Pt(866898),emissiveIntensity:.6,side:de}),floor:new Me({map:t,color:10134448,metalness:.25,roughness:.85,side:de}),ceiling:new Me({map:e,color:9279139,metalness:.3,roughness:.8,side:de}),trim:new Me({color:1192e3,emissive:new Pt(3725567),emissiveIntensity:1.6,metalness:.2,roughness:.4}),glass:new jm({color:11066623,metalness:0,roughness:.06,transmission:.85,transparent:!0,opacity:.32,side:de,depthWrite:!1}),prop:new Me({color:7108228,metalness:.6,roughness:.5}),emissive:new fe({color:9431295}),screen:new fe({color:662052})}}function hc(i,t="",e={}){const n=e.width??512,s=e.height??160,r=e.accent||"#4fd8ff",a=document.createElement("canvas");a.width=n,a.height=s;const o=a.getContext("2d");o.fillStyle="#0b1218",o.fillRect(0,0,n,s),o.strokeStyle=r,o.lineWidth=4,o.strokeRect(4,4,n-8,s-8),o.fillStyle=r,o.fillRect(4,4,96,s-8),o.fillStyle="#04121a",o.font='bold 64px "Segoe UI", system-ui, sans-serif',o.textAlign="center",o.textBaseline="middle",o.fillText("◈",52,s/2+2),o.fillStyle="#e8f6ff",o.textAlign="left",o.font='bold 56px "Microsoft YaHei", "PingFang SC", system-ui, sans-serif',o.fillText(i,124,t?s/2-18:s/2),t&&(o.fillStyle="#7fb8d4",o.font='30px "Microsoft YaHei", "PingFang SC", system-ui, sans-serif',o.fillText(t,124,s/2+34));const l=new Za(a);return l.anisotropy=4,l}function Os(i,t,e,n,s=32,r=6,a=.07){const o=[],l=[],h=[],d=[];for(let f=0;f<=r;f+=1){const g=f/r,v=(.5-g)*t,m=i-Math.sin(g*Math.PI)*a;for(let p=0;p<=s;p+=1){const y=p/s,_=e+y*n,S=Math.sin(_)*m,P=Math.cos(_)*m;o.push(S,v,P),l.push(-Math.sin(_),0,-Math.cos(_)),h.push(y,1-g)}}const c=s+1;for(let f=0;f<r;f+=1)for(let g=0;g<s;g+=1){const v=f*c+g,m=v+1,p=v+c,y=p+1;d.push(v,m,p,m,y,p)}const u=new Le;return u.setAttribute("position",new le(o,3)),u.setAttribute("normal",new le(l,3)),u.setAttribute("uv",new le(h,2)),u.setIndex(d),u.computeBoundingSphere(),u}class F0{group=new Ze;mesh;canvas;texture;radius;height;thetaStart;thetaLength;glow;rimTop;rimBottom;accent;constructor(t){const e=t.canvasWidth??1024,n=t.canvasHeight??576;this.canvas=document.createElement("canvas"),this.canvas.width=e,this.canvas.height=n,this.texture=new Za(this.canvas),this.texture.colorSpace=je,this.texture.generateMipmaps=!1,this.texture.minFilter=We,this.texture.magFilter=We,this.texture.wrapS=xn,this.texture.wrapT=xn,this.radius=t.radius??1.55,this.height=t.screenHeight??.95,this.thetaLength=t.thetaLength??1.15,this.thetaStart=Math.PI-this.thetaLength/2,this.accent=new Pt(t.accent),this.mesh=new Ct(Os(this.radius,this.height,this.thetaStart,this.thetaLength),new fe({map:this.texture,transparent:!0,opacity:.96,side:hn,depthWrite:!1,toneMapped:!1})),this.mesh.name="holo-screen",this.group.add(this.mesh),this.glow=new Ct(Os(this.radius+.02,this.height*1.08,this.thetaStart,this.thetaLength,32,4,.08),new fe({color:this.accent,transparent:!0,opacity:.16,side:de,blending:Ai,depthWrite:!1})),this.group.add(this.glow);const s=new fe({color:this.accent,transparent:!0,opacity:.95,side:de,toneMapped:!1}),r=Os(this.radius+.015,.05,this.thetaStart-.02,this.thetaLength+.04,32,1,0);if(this.rimTop=new Ct(r,s),this.rimTop.position.y=this.height/2+.03,this.rimBottom=new Ct(r,s),this.rimBottom.position.y=-this.height/2-.03,this.group.add(this.rimTop,this.rimBottom),t.withPedestal!==!1){const o=new Ct(new Jn(.16,.24,.9,12),new Me({color:5923954,metalness:.8,roughness:.4}));o.position.y=-this.height/2-.45;const l=new Ct(new Jn(.55,.62,.12,16),new Me({color:4344406,metalness:.7,roughness:.5}));l.position.y=-this.height/2-.92;const h=new Ct(new ti(.5,.03,6,28),new fe({color:this.accent,transparent:!0,opacity:.7,toneMapped:!1}));h.rotation.x=Math.PI/2,h.position.y=-this.height/2-.86,this.group.add(o,l,h)}const a=new Ct(Os(this.radius*.98,this.height*.55,this.thetaStart,this.thetaLength,24,2,.02),new fe({color:this.accent,transparent:!0,opacity:.07,side:de,blending:Ai,depthWrite:!1}));a.position.y=-this.height/2-.24,this.group.add(a)}setAccent(t){this.accent.setHex(t),this.glow.material.color.setHex(t),this.rimTop.material.color.setHex(t)}worldCenter(t=new R){return this.mesh.getWorldPosition(t)}dispose(){this.texture.dispose(),this.group.traverse(t=>{const e=t;e.geometry&&e.geometry.dispose();const n=e.material;Array.isArray(n)?n.forEach(s=>s.dispose()):n?.dispose()})}}function O0(i,t){const e=new Ze,n=new F0({canvasWidth:1024,canvasHeight:576,accent:t.accent,radius:1.7,screenHeight:1.05,thetaLength:1.2});n.group.position.set(0,1.35,0),e.add(n.group);const s=new Ct(new Te(1.5,.08,.42),new Me({color:4937059,metalness:.7,roughness:.45}));s.position.set(0,.76,1.28),e.add(s);const r=new Ct(new Te(1.42,.02,.34),new fe({color:t.accent,transparent:!0,opacity:.3,toneMapped:!1}));return r.position.set(0,.81,1.28),e.add(r),{group:e,screen:n}}function B0(i){return{accent:i,accentDim:Ge(i,.35),text:"#e6f4ff",textDim:"#8fb0c8",ok:"#4fe0a0",warn:"#ffc861",error:"#ff7b7b",panel:"rgba(10, 26, 38, 0.72)",panelEdge:Ge(i,.55),grid:"rgba(80, 180, 220, 0.08)"}}function Ge(i,t){const e=i.replace("#",""),n=parseInt(e.slice(0,2),16),s=parseInt(e.slice(2,4),16),r=parseInt(e.slice(4,6),16);return"rgba("+n+","+s+","+r+","+t+")"}const ji='"Microsoft YaHei", "PingFang SC", "Segoe UI", system-ui, sans-serif',gl='"JetBrains Mono", "Cascadia Mono", Consolas, monospace';class k0{canvas;ctx;theme;cursor={x:0,y:0,inside:!1,down:!1};hoverId=null;hits=[];previousHits=[];scroll=new Map;time=0;width;height;constructor(t,e,n,s){this.width=t,this.height=e,this.canvas=s??document.createElement("canvas"),this.canvas.width=t,this.canvas.height=e;const r=this.canvas.getContext("2d");if(!r)throw new Error("无法创建 2D 画布上下文");this.ctx=r,this.theme=B0(n)}begin(t,e,n){this.time+=t,this.previousHits=this.hits,this.hits=[];const s=this.ctx;s.save(),s.setTransform(1,0,0,1,0,0),s.clearRect(0,0,this.width,this.height);const r=s.createLinearGradient(0,0,this.width,this.height);r.addColorStop(0,"rgba(4, 14, 22, 0.96)"),r.addColorStop(.55,"rgba(6, 20, 30, 0.94)"),r.addColorStop(1,"rgba(3, 10, 18, 0.97)"),s.fillStyle=r,s.fillRect(0,0,this.width,this.height),s.strokeStyle=this.theme.grid,s.lineWidth=1;for(let a=0;a<this.width;a+=32)s.beginPath(),s.moveTo(a+.5,0),s.lineTo(a+.5,this.height),s.stroke();for(let a=0;a<this.height;a+=32)s.beginPath(),s.moveTo(0,a+.5),s.lineTo(this.width,a+.5),s.stroke();s.fillStyle="rgba(120, 220, 255, 0.025)";for(let a=0;a<this.height;a+=4)s.fillRect(0,a,this.width,1);s.fillStyle=Ge(this.theme.accent,.14),s.fillRect(0,0,this.width,64),s.fillStyle=this.theme.accent,s.fillRect(0,62,this.width,2),s.font="bold 30px "+ji,s.fillStyle=this.theme.text,s.textAlign="left",s.textBaseline="middle",s.fillText(e,24,33),s.font="18px "+ji,s.fillStyle=this.theme.textDim,s.textAlign="right",s.fillText(n,this.width-24,34),s.textAlign="left"}end(){const t=this.ctx;if(this.cursor.inside){const{x:r,y:a}=this.cursor;t.save(),t.strokeStyle=this.theme.accent,t.lineWidth=2,t.beginPath(),t.moveTo(r-12,a),t.lineTo(r-4,a),t.moveTo(r+4,a),t.lineTo(r+12,a),t.moveTo(r,a-12),t.lineTo(r,a-4),t.moveTo(r,a+4),t.lineTo(r,a+12),t.stroke(),t.beginPath(),t.arc(r,a,3.5,0,Math.PI*2),t.stroke(),t.restore()}t.strokeStyle=Ge(this.theme.accent,.8),t.lineWidth=3;const e=26,n=8,s=[[n,n,1,1],[this.width-n,n,-1,1],[n,this.height-n,1,-1],[this.width-n,this.height-n,-1,-1]];for(const[r,a,o,l]of s)t.beginPath(),t.moveTo(r+o*e,a),t.lineTo(r,a),t.lineTo(r,a+l*e),t.stroke();t.restore()}text(t,e,n,s={}){const r=this.ctx;r.font=(s.weight?s.weight+" ":"")+(s.size??18)+"px "+(s.mono?gl:ji),r.fillStyle=s.color||this.theme.text,r.textAlign=s.align||"left",r.textBaseline=s.baseline||"alphabetic",s.maxWidth?r.fillText(n,t,e,s.maxWidth):r.fillText(n,t,e)}panel(t,e={}){const n=this.ctx;n.save(),n.fillStyle=this.theme.panel,n.fillRect(t.x,t.y,t.w,t.h),n.strokeStyle=e.tone||this.theme.panelEdge,n.lineWidth=1.5,n.strokeRect(t.x+.5,t.y+.5,t.w-1,t.h-1);const s=14;n.beginPath(),n.moveTo(t.x,t.y+s),n.lineTo(t.x+s,t.y),n.moveTo(t.x+t.w-s,t.y),n.lineTo(t.x+t.w,t.y+s),n.moveTo(t.x,t.y+t.h-s),n.lineTo(t.x+s,t.y+t.h),n.moveTo(t.x+t.w-s,t.y+t.h),n.lineTo(t.x+t.w,t.y+t.h-s),n.strokeStyle=e.tone||this.theme.accent,n.lineWidth=3,n.stroke(),e.title&&(n.fillStyle=e.tone||this.theme.accent,n.font="bold 19px "+ji,this.text(t.x+14,t.y+24,e.title,{size:19,weight:"bold",color:e.tone||this.theme.accent}),n.fillStyle=Ge("#ffffff",.06),n.fillRect(t.x+1,t.y+34,t.w-2,1)),n.restore()}hit(t,e){this.hits.push({id:t,rect:e});const n=this.cursor.x>=e.x&&this.cursor.x<=e.x+e.w&&this.cursor.y>=e.y&&this.cursor.y<=e.y+e.h;return n&&(this.hoverId=t),n}isHovered(t){return this.hoverId===t}hoverRect(t,e){this.hits.push({id:t,rect:e});const n=this.cursor.x>=e.x&&this.cursor.x<=e.x+e.w&&this.cursor.y>=e.y&&this.cursor.y<=e.y+e.h;return n&&(this.hoverId=t),n}button(t,e,n,s={}){const r=this.ctx,a=this.hoverRect(t,e),o=s.tone||this.theme.accent;return r.save(),r.fillStyle=s.disabled?"rgba(60,70,80,0.35)":a?Ge(o,.32):Ge(o,.12),r.fillRect(e.x,e.y,e.w,e.h),r.strokeStyle=s.disabled?"rgba(120,130,140,0.4)":o,r.lineWidth=a?2.5:1.5,r.strokeRect(e.x+.5,e.y+.5,e.w-1,e.h-1),r.font="bold "+(s.size??18)+"px "+ji,r.fillStyle=s.disabled?"rgba(180,190,200,0.5)":this.theme.text,r.textAlign="center",r.textBaseline="middle",r.fillText(n,e.x+e.w/2,e.y+e.h/2+1,e.w-12),r.restore(),s.disabled?!1:a&&this.clicked}clicked=!1;toggle(t,e,n,s){const r=this.ctx,a=this.hoverRect(t,e);r.save(),r.fillStyle=a?"rgba(40,60,80,0.6)":"rgba(20,32,44,0.55)",r.fillRect(e.x,e.y,e.w,e.h),r.strokeStyle=s?this.theme.ok:this.theme.textDim,r.lineWidth=1.5,r.strokeRect(e.x+.5,e.y+.5,e.w-1,e.h-1);const o=46,l=e.x+e.w-o-14,h=e.y+e.h/2-6;return r.fillStyle=s?Ge(this.theme.ok,.35):"rgba(90,100,110,0.45)",r.fillRect(l,h,o,12),r.fillStyle=s?this.theme.ok:"#8a949e",r.fillRect(s?l+o-12:l,h-3,12,18),this.text(e.x+12,e.y+e.h/2+6,n,{size:17}),r.restore(),a&&this.clicked}progress(t,e,n={}){const s=this.ctx,r=n.color||this.theme.accent,a=Math.max(0,Math.min(1,e));s.save(),s.fillStyle="rgba(16, 30, 42, 0.85)",s.fillRect(t.x,t.y,t.w,t.h);const o=s.createLinearGradient(t.x,0,t.x+t.w,0);o.addColorStop(0,Ge(r,.55)),o.addColorStop(1,r),s.fillStyle=o,s.fillRect(t.x,t.y,t.w*a,t.h),s.strokeStyle=Ge(r,.7),s.lineWidth=1,s.strokeRect(t.x+.5,t.y+.5,t.w-1,t.h-1),n.label&&this.text(t.x,t.y-6,n.label,{size:15,color:this.theme.textDim}),n.showValue!==!1&&this.text(t.x+t.w-8,t.y+t.h/2+6,(a*100).toFixed(0)+"%"+(n.suffix||""),{size:15,align:"right",color:this.theme.text}),s.restore()}sparkline(t,e,n={}){const s=this.ctx,r=n.color||this.theme.accent;if(s.save(),s.fillStyle="rgba(10, 22, 32, 0.6)",s.fillRect(t.x,t.y,t.w,t.h),e.length>1){const a=Math.max(...e,1),o=Math.min(...e,0),l=Math.max(a-o,1);s.beginPath(),e.forEach((h,d)=>{const c=t.x+d/(e.length-1)*t.w,u=t.y+t.h-(h-o)/l*(t.h-12)-6;d===0?s.moveTo(c,u):s.lineTo(c,u)}),s.strokeStyle=r,s.lineWidth=2,s.stroke(),n.fill&&(s.lineTo(t.x+t.w,t.y+t.h),s.lineTo(t.x,t.y+t.h),s.closePath(),s.fillStyle=Ge(r,.16),s.fill())}s.strokeStyle=Ge(r,.5),s.lineWidth=1,s.strokeRect(t.x+.5,t.y+.5,t.w-1,t.h-1),n.label&&this.text(t.x+8,t.y+20,n.label,{size:15,color:this.theme.textDim}),n.valueText&&this.text(t.x+t.w-8,t.y+20,n.valueText,{size:16,align:"right",color:this.theme.text}),s.restore()}bars(t,e,n={}){const s=this.ctx,r=n.max??Math.max(...e.map(o=>o.value),1),a=Math.min(26,(t.h-8)/Math.max(e.length,1)-6);s.save(),e.forEach((o,l)=>{const h=t.y+l*(a+6),d=120,c=t.w-d-70;this.text(t.x,h+a-6,o.label,{size:15,color:this.theme.textDim,maxWidth:d-8}),s.fillStyle="rgba(20, 36, 50, 0.8)",s.fillRect(t.x+d,h,c,a);const u=Math.max(0,Math.min(1,o.value/r));s.fillStyle=o.color||this.theme.accent,s.fillRect(t.x+d,h,c*u,a),this.text(t.x+t.w,h+a-6,String(o.value),{size:15,align:"right",color:this.theme.text})}),s.restore()}list(t,e,n,s={}){const r=this.ctx,a=s.rowHeight??44,o=s.scrollable===!1?0:this.scroll.get(t)??0,l=Math.floor(e.h/a),h=Math.max(0,n.length-l),d=Math.max(0,Math.min(h,Math.round(o)));this.scroll.set(t,d),r.save(),r.beginPath(),r.rect(e.x,e.y,e.w,e.h),r.clip(),r.fillStyle="rgba(8, 20, 30, 0.5)",r.fillRect(e.x,e.y,e.w,e.h);let c=-1;for(let u=d;u<Math.min(n.length,d+l+1);u+=1){const f=n[u],g=e.y+(u-d)*a,v={x:e.x,y:g,w:e.w-(h>0?10:0),h:a-2},m=this.hoverRect(t+":"+u,v);m&&this.clicked&&(c=u),r.fillStyle=m?"rgba(60, 120, 160, 0.35)":f.active?"rgba(40, 90, 120, 0.35)":u%2===0?"rgba(12, 26, 38, 0.45)":"rgba(10, 22, 32, 0.35)",r.fillRect(v.x,v.y,v.w,v.h),f.tone&&(r.fillStyle=f.tone,r.fillRect(e.x,g,3,a-2)),this.text(e.x+14,g+(f.sub?19:a/2+4),f.label,{size:17,maxWidth:e.w-140}),f.sub&&this.text(e.x+14,g+36,f.sub,{size:14,color:this.theme.textDim,maxWidth:e.w-140}),f.badge&&this.text(e.x+e.w-20,g+a/2+4,f.badge,{size:14,align:"right",color:this.theme.textDim})}if(r.restore(),h>0){const u=e.h,f=Math.max(28,l/n.length*u),g=e.y+d/h*(u-f);r.fillStyle="rgba(80, 140, 180, 0.35)",r.fillRect(e.x+e.w-6,g,5,f)}return c}keyValue(t,e,n,s,r,a){this.text(t,e,s,{size:16,color:this.theme.textDim}),this.text(t+n,e,r,{size:17,align:"right",color:a||this.theme.text})}textField(t,e,n,s={}){const r=this.ctx,a=this.hoverRect(t,e),o=a&&this.clicked;r.save(),r.fillStyle=s.focused?"rgba(20, 50, 70, 0.85)":"rgba(14, 28, 40, 0.75)",r.fillRect(e.x,e.y,e.w,e.h),r.strokeStyle=s.focused?this.theme.accent:Ge(this.theme.accent,.4),r.lineWidth=s.focused?2:1,r.strokeRect(e.x+.5,e.y+.5,e.w-1,e.h-1),r.beginPath(),r.rect(e.x+6,e.y+4,e.w-12,e.h-8),r.clip();const l=n||s.placeholder||"";if(r.font=(s.multiline?"16px ":"17px ")+gl,r.fillStyle=n?this.theme.text:this.theme.textDim,(s.multiline?l.split(`
`).slice(0,Math.floor(e.h/20)):[l]).forEach((d,c)=>{r.fillText(d,e.x+10,e.y+24+c*20)}),s.focused&&Math.floor(this.time*2)%2===0){const d=s.caret??n.length,c=n.slice(0,d),u=r.measureText(c).width;r.fillStyle=this.theme.accent,r.fillRect(e.x+10+u+1,e.y+8,2,e.h-16)}return r.restore(),{clicked:o,hovered:a}}gauge(t,e,n,s={}){const r=this.ctx,a=s.color||this.theme.accent,o=Math.max(0,Math.min(1,n));r.save(),r.lineWidth=10,r.strokeStyle="rgba(30, 50, 66, 0.9)",r.beginPath(),r.arc(t.x,t.y,e,Math.PI*.75,Math.PI*.25+Math.PI*2*.999),r.stroke(),r.strokeStyle=a,r.beginPath(),r.arc(t.x,t.y,e,Math.PI*.75,Math.PI*.75+o*Math.PI*1.5),r.stroke(),r.fillStyle=a;for(let l=0;l<=24;l+=1){const h=Math.PI*.75+l/24*Math.PI*1.5,d=e-16,c=e-11;r.globalAlpha=l/24<=o?1:.25,r.beginPath(),r.moveTo(t.x+Math.cos(h)*d,t.y+Math.sin(h)*d),r.lineTo(t.x+Math.cos(h)*c,t.y+Math.sin(h)*c),r.lineWidth=2,r.strokeStyle=a,r.stroke()}r.globalAlpha=1,s.valueText&&this.text(t.x,t.y+8,s.valueText,{size:26,align:"center",color:this.theme.text,weight:"bold"}),s.label&&this.text(t.x,t.y+e-6,s.label,{size:15,align:"center",color:this.theme.textDim}),r.restore()}scrollBy(t,e){const n=this.scroll.get(t)??0;this.scroll.set(t,n+e)}scrollReset(t){this.scroll.set(t,0)}hitTest(t,e){for(let n=this.previousHits.length-1;n>=0;n-=1){const s=this.previousHits[n];if(t>=s.rect.x&&t<=s.rect.x+s.rect.w&&e>=s.rect.y&&e<=s.rect.y+s.rect.h)return s.id}return null}}const z0=16754237;class H0{constructor(t,e,n){this.host=e,this.definition=t,this.anchor=n,this.baseAccent=t.accent;const s=O0(e.materials,{accent:t.accent,title:t.title});this.screen=s.screen,this.group.add(s.group),t.decorate?.(this.group,e.materials);const r=new Ct(new Qn(1.15,.36),new fe({map:hc(t.title,t.subtitle,{width:512,height:160,accent:"#"+t.accent.toString(16).padStart(6,"0")}),transparent:!0,side:de}));r.position.set(0,2.42,-.9),this.group.add(r),this.group.position.copy(n.position),this.group.rotation.y=n.yaw,e.scene.add(this.group),this.ui=new k0(this.screen.canvas.width,this.screen.canvas.height,"#33d6ff",this.screen.canvas),this.controller=t.create?t.create({host:e,anchor:n,ui:this.ui,shell:e.shell,redraw:()=>this.markDirty(),toast:e.toast,confirm:e.confirm}):null,this.drawFrame(!0)}definition;anchor;group=new Ze;screen;ui;controller=null;active=!1;dirty=!0;idleAccumulator=0;availability={available:!0,reason:"",hint:"",readOnly:!1};baseAccent;disposed=!1;override=null;get available(){return this.availability.available}get focused(){return this.active}get interactable(){return this.availability.available}get availabilityReason(){return this.availability.reason||"当前状态不可用"}markDirty(){this.dirty=!0}setOverride(t){this.override=t,this.markDirty()}setAvailability(t){const e=t.available!==this.availability.available||t.reason!==this.availability.reason||t.readOnly!==this.availability.readOnly;this.availability=t,this.screen.setAccent(t.available?this.baseAccent:z0),e&&this.markDirty()}focusView(){const t=new R(0,0,1).applyAxisAngle(new R(0,1,0),this.anchor.yaw),e=this.screen.radius+.75,n=this.anchor.position.clone().add(t.multiplyScalar(e)).add(new R(0,1.52,0)),s=this.screen.worldCenter(new R);return{position:n,target:s}}focus(){if(!this.active){this.active=!0,this.controller?.onFocus?.();for(const t of this.controller?.pollers??[])t.start(!0);this.markDirty()}}blur(){if(this.active){this.active=!1,this.controller?.onBlur?.();for(const t of this.controller?.pollers??[])t.stop();this.markDirty()}}handlePointer(t,e,n){if(!t||!t.uv){this.ui.cursor.inside=!1;return}const s=t.uv.x*this.ui.width,r=(1-t.uv.y)*this.ui.height,a=Math.abs(s-this.ui.cursor.x)>.5||Math.abs(r-this.ui.cursor.y)>.5;if(this.ui.cursor.x=s,this.ui.cursor.y=r,this.ui.cursor.inside=!0,e&&(this.ui.clicked=!0,this.markDirty()),a&&this.markDirty(),n!==0){const o=this.ui.hitTest(s,r);if(o){const l=o.split(":")[0];this.ui.scrollBy(l,n*.05),this.markDirty()}}}update(t){if(this.disposed)return;const e=this.active;if(!e){this.ui.cursor.inside=!1;const n=this.definition.id!==""&&this.controller?.idleAnimated===!0,s=this.host.quality.refreshIdleTerminals?1:n?.4:0;s>0&&(this.idleAccumulator+=t,this.idleAccumulator>=s&&(this.idleAccumulator=0,this.markDirty()))}this.dirty&&(this.drawFrame(e),this.dirty=!1)}drawFrame(t){const e=this.ui;if(e.clicked=!1,e.hoverId=null,!this.availability.available){this.drawOffline(e),e.end();return}e.begin(1/30,this.definition.title,this.definition.subtitle),this.availability.reason&&(e.text(24,92,"⚠ "+this.availability.reason,{size:17,color:e.theme.warn}),this.availability.hint&&e.text(24,116,this.availability.hint,{size:15,color:e.theme.textDim})),this.override?this.override(e,t):this.controller?.draw(e,t),e.end(),this.screen.texture.needsUpdate=!0}drawOffline(t){const e=t.ctx,n=performance.now()/1e3,s=t.width,r=t.height;e.save(),e.fillStyle="rgba(4, 8, 12, 0.97)",e.fillRect(0,0,s,r),e.strokeStyle="rgba(255, 166, 61, 0.35)",e.lineWidth=2;for(let a=0;a<14;a+=1){const o=(a/14*r+n*26)%r;e.beginPath(),e.moveTo(0,o),e.lineTo(s,o),e.stroke()}e.fillStyle="rgba(255, 166, 61, "+(.55+.35*Math.sin(n*3)).toFixed(3)+")",e.font='bold 42px "Microsoft YaHei", system-ui, sans-serif',e.textAlign="center",e.fillText("终 端 已 下 线",s/2,r/2-60),e.font='24px "Microsoft YaHei", system-ui, sans-serif',e.fillStyle="rgba(255, 200, 150, 0.9)",e.fillText(this.availability.reason||"该面板当前不可用",s/2,r/2+4),this.availability.hint&&(e.font='20px "Microsoft YaHei", system-ui, sans-serif',e.fillStyle="rgba(200, 220, 235, 0.75)",e.fillText(this.availability.hint,s/2,r/2+44)),e.font='18px "Microsoft YaHei", system-ui, sans-serif',e.fillStyle="rgba(255, 166, 61, 0.7)",e.fillText("LOW POWER MODE · "+this.definition.title,s/2,r-40),e.restore()}dispose(){this.disposed||(this.disposed=!0,this.blur(),this.controller?.dispose?.(),this.host.scene.remove(this.group),this.screen.dispose())}}function uc(i,t=!1){const e=i[0].index!==null,n=new Set(Object.keys(i[0].attributes)),s=new Set(Object.keys(i[0].morphAttributes)),r={},a={},o=i[0].morphTargetsRelative,l=new Le;let h=0;for(let d=0;d<i.length;++d){const c=i[d];let u=0;if(e!==(c.index!==null))return console.error("THREE.BufferGeometryUtils: .mergeGeometries() failed with geometry at index "+d+". All geometries must have compatible attributes; make sure index attribute exists among all geometries, or in none of them."),null;for(const f in c.attributes){if(!n.has(f))return console.error("THREE.BufferGeometryUtils: .mergeGeometries() failed with geometry at index "+d+'. All geometries must have compatible attributes; make sure "'+f+'" attribute exists among all geometries, or in none of them.'),null;r[f]===void 0&&(r[f]=[]),r[f].push(c.attributes[f]),u++}if(u!==n.size)return console.error("THREE.BufferGeometryUtils: .mergeGeometries() failed with geometry at index "+d+". Make sure all geometries have the same number of attributes."),null;if(o!==c.morphTargetsRelative)return console.error("THREE.BufferGeometryUtils: .mergeGeometries() failed with geometry at index "+d+". .morphTargetsRelative must be consistent throughout all geometries."),null;for(const f in c.morphAttributes){if(!s.has(f))return console.error("THREE.BufferGeometryUtils: .mergeGeometries() failed with geometry at index "+d+".  .morphAttributes must be consistent throughout all geometries."),null;a[f]===void 0&&(a[f]=[]),a[f].push(c.morphAttributes[f])}if(t){let f;if(e)f=c.index.count;else if(c.attributes.position!==void 0)f=c.attributes.position.count;else return console.error("THREE.BufferGeometryUtils: .mergeGeometries() failed with geometry at index "+d+". The geometry must have either an index or a position attribute"),null;l.addGroup(h,f,d),h+=f}}if(e){let d=0;const c=[];for(let u=0;u<i.length;++u){const f=i[u].index;for(let g=0;g<f.count;++g)c.push(f.getX(g)+d);d+=i[u].attributes.position.count}l.setIndex(c)}for(const d in r){const c=_l(r[d]);if(!c)return console.error("THREE.BufferGeometryUtils: .mergeGeometries() failed while trying to merge the "+d+" attribute."),null;l.setAttribute(d,c)}for(const d in a){const c=a[d][0].length;if(c===0)break;l.morphAttributes=l.morphAttributes||{},l.morphAttributes[d]=[];for(let u=0;u<c;++u){const f=[];for(let v=0;v<a[d].length;++v)f.push(a[d][v][u]);const g=_l(f);if(!g)return console.error("THREE.BufferGeometryUtils: .mergeGeometries() failed while trying to merge the "+d+" morphAttribute."),null;l.morphAttributes[d].push(g)}}return l}function _l(i){let t,e,n,s=-1,r=0;for(let h=0;h<i.length;++h){const d=i[h];if(t===void 0&&(t=d.array.constructor),t!==d.array.constructor)return console.error("THREE.BufferGeometryUtils: .mergeAttributes() failed. BufferAttribute.array must be of consistent array types across matching attributes."),null;if(e===void 0&&(e=d.itemSize),e!==d.itemSize)return console.error("THREE.BufferGeometryUtils: .mergeAttributes() failed. BufferAttribute.itemSize must be consistent across matching attributes."),null;if(n===void 0&&(n=d.normalized),n!==d.normalized)return console.error("THREE.BufferGeometryUtils: .mergeAttributes() failed. BufferAttribute.normalized must be consistent across matching attributes."),null;if(s===-1&&(s=d.gpuType),s!==d.gpuType)return console.error("THREE.BufferGeometryUtils: .mergeAttributes() failed. BufferAttribute.gpuType must be consistent across matching attributes."),null;r+=d.count*e}const a=new t(r),o=new Xe(a,e,n);let l=0;for(let h=0;h<i.length;++h){const d=i[h];if(d.isInterleavedBufferAttribute){const c=l/e;for(let u=0,f=d.count;u<f;u++)for(let g=0;g<e;g++){const v=d.getComponent(u,g);o.setComponent(u+c,g,v)}}else a.set(d.array,l);l+=d.count*e}return s!==void 0&&(o.gpuType=s),o}const Mt=4,Si=30,wi=10,es=[0,4.4,8.8],zt=3.6,xl={E:"engineering",H:"hangar",G:"cargo",B:"bridge",K:"lounge",D:"medbay",S:"science",A:"archive",M:"command",O:"observation",c:"corridor"},vl={bridge:{id:"bridge",label:"舰桥",description:"全舰指挥中枢，主控台与通讯台都在这里。",windows:!0},corridor:{id:"corridor",label:"主走廊",description:"连接各舱室的通道。",windows:!1},engineering:{id:"engineering",label:"工程舱",description:"反应堆、能量分配与插件模块机架。",windows:!1},hangar:{id:"hangar",label:"机库",description:"舰载机与损管设备停放区，兼作抢修训练场。",windows:!0},cargo:{id:"cargo",label:"货舱",description:"补给与舰船战绩档案。",windows:!1},lounge:{id:"lounge",label:"休息厅",description:"船员休息区：咖啡机与点唱机。",windows:!0},medbay:{id:"medbay",label:"医务室",description:"生命体征与舰员健康监控。",windows:!0},science:{id:"science",label:"科学舱",description:"神经矩阵与提示词分析仪。",windows:!1},archive:{id:"archive",label:"档案舱",description:"航行日志与历史记录。",windows:!0},command:{id:"command",label:"指挥室",description:"舰载系统配置与权限管理。",windows:!0},observation:{id:"observation",label:"观景廊",description:"全舰视野最好的地方，也是舷侧炮塔的操炮位。",windows:!0}},G0=["##############################","#............................#","#EEEEEEEEE........HHHHHHHHHH.#","#EEEEEEEEE........HHHHHHHHHH.#","#EEEEEEEEEccccccccHHHHHHHHHH.#","#EEEEEEEEE........HHHHHHHHHH.#","#EEEEEEEEE........HHHHHHHHHH.#","#....GGGGGGGGGGGGGGGGGGGG....#","#............................#","##############################"],V0=["##############################","#............................#","#BBBBBBBBBBB..........KKKKKKK#","#BBBBBBBBBBB..........KKKKKKK#","#BBBBBBBBBBBccccccccccccccccc#","#BBBBBBBBBBB..........DDDDDDD#","#BBBBBBBBBBB..........DDDDDDD#","#............................#","#............................#","##############################"],W0=["##############################","#............................#","#SSSSSSSSSS.......AAAAAAAAAAA#","#SSSSSSSSSS.......AAAAAAAAAAA#","#cccccccccccccccccccccccccccc#","#MMMMMMMMMMOOOOOOOOOOOOOOOOOO#","#MMMMMMMMMMOOOOOOOOOOOOOOOOOO#","#............................#","#............................#","##############################"],ke=[{name:"工程甲板",y:es[0],rows:G0},{name:"主甲板",y:es[1],rows:V0},{name:"科学甲板",y:es[2],rows:W0}],Ml=[{col:10,row:4,fromDeck:0,toDeck:1},{col:25,row:5,fromDeck:0,toDeck:1},{col:13,row:4,fromDeck:1,toDeck:2},{col:24,row:4,fromDeck:1,toDeck:2}],X0=[{id:"bridge-main",room:"bridge",offset:[-7,-4.5],yaw:-Math.PI/2,label:"主控台",hint:"舰船总览与实时指标",kind:"terminal",target:"dashboard"},{id:"bridge-comms",room:"bridge",offset:[-7,4.5],yaw:-Math.PI/2,label:"通讯台",hint:"机器人与会话状态",kind:"terminal",target:"bots"},{id:"bridge-nav",room:"bridge",offset:[-13.5,0],yaw:Math.PI/2,label:"星图导航台",hint:"设定航线 / 触发跃迁",kind:"prop",target:"navigation"},{id:"bridge-captain",room:"bridge",offset:[10,0],yaw:Math.PI/2,label:"舰长席",hint:"坐下观察全舰",kind:"prop",target:"captain-chair"},{id:"lounge-coffee",room:"lounge",offset:[-4,-3],yaw:0,label:"咖啡机",hint:"来一杯舰载合成咖啡",kind:"prop",target:"coffee"},{id:"lounge-jukebox",room:"lounge",offset:[4,3],yaw:0,label:"点唱机",hint:"播放一段合成音律",kind:"prop",target:"jukebox"},{id:"medbay-vitals",room:"medbay",offset:[-6,0],yaw:-Math.PI/2,label:"生命体征仪",hint:"舰体资源与进程状态",kind:"prop",target:"vitals"},{id:"medbay-kit",room:"medbay",offset:[5,0],yaw:Math.PI/2,label:"医疗补给柜",hint:"补齐随身物资",kind:"prop",target:"supplies"},{id:"eng-reactor",room:"engineering",offset:[-13,0],yaw:-Math.PI/2,label:"反应堆监控",hint:"系统资源与进程",kind:"terminal",target:"system"},{id:"eng-power",room:"engineering",offset:[0,-6],yaw:0,label:"能量分配",hint:"模型用量与开销",kind:"terminal",target:"usage"},{id:"eng-racks",room:"engineering",offset:[0,6],yaw:Math.PI,label:"模块机架",hint:"插件装载与启停",kind:"terminal",target:"plugins"},{id:"eng-repair",room:"engineering",offset:[13,0],yaw:Math.PI/2,label:"损管终端",hint:"进入损管抢修演练",kind:"minigame",target:"repair"},{id:"hangar-turret",room:"hangar",offset:[0,-7],yaw:0,label:"炮塔模拟器",hint:"进入舱外炮塔演练",kind:"minigame",target:"turret"},{id:"hangar-crate",room:"hangar",offset:[10,6],yaw:0,label:"补给箱",hint:"检查舰载补给",kind:"prop",target:"supplies"},{id:"cargo-scores",room:"cargo",offset:[0,0],yaw:0,label:"战绩墙",hint:"小游戏排行榜与成就",kind:"terminal",target:"scores"},{id:"sci-matrix",room:"science",offset:[0,0],yaw:0,label:"神经矩阵",hint:"提示词与 Agent 分析",kind:"terminal",target:"analysis"},{id:"archive-logs",room:"archive",offset:[0,-3],yaw:0,label:"航行日志",hint:"实时运行日志",kind:"terminal",target:"logs"},{id:"command-config",room:"command",offset:[0,-4],yaw:0,label:"舰载系统配置",hint:"本体配置与环境变量",kind:"terminal",target:"config"},{id:"obs-turret",room:"observation",offset:[16,2],yaw:Math.PI,label:"舷侧炮塔",hint:"进入舱外炮塔演练",kind:"minigame",target:"turret"},{id:"obs-scope",room:"observation",offset:[-6,1],yaw:0,label:"天文望远镜",hint:"观察舰外天体",kind:"prop",target:"telescope"}];function Xn(i){return(i-Si/2)*Mt}function Yn(i){return(i-wi/2)*Mt}function yl(i,t){return[Xn(i)+Mt/2,Yn(t)+Mt/2]}function Sl(i,t,e){if(e<0||e>=i.rows.length)return"#";const n=i.rows[e]??"";return t<0||t>=n.length?"#":n[t]}function wl(i){return i!=="#"&&i!=="."&&i!==" "}const Rn=2.5,ze=2.6,Gn=1,He=2.55;function Yt(i,t,e,n,s,r){const a=new Te(i,t,e);return a.translate(n,s,r),a}function Vr(i,t){return i===0||i===Si-1||t===0||t===wi-1}function _i(i,t,e,n,s,r,a,o,l="wall"){i.push(Yt(e,n,s,r,a,o)),t.add(new R(r-e/2,a-n/2,o-s/2),new R(r+e/2,a+n/2,o+s/2),l)}function Y0(i,t,e){const n=new Ze;n.name="starship";const s=N0(),r=[],a=new Map,o=[],l=[],h=[],d=[],c=[],u=[],f=[],g=[],v=[],m=new Set;for(const G of Ml)m.add(G.fromDeck+":"+G.col+":"+G.row),m.add(G.toDeck+":"+G.col+":"+G.row);const p=new Map;e?.("正在铺设甲板结构…"),ke.forEach((G,I)=>{const F=G.y;for(let O=0;O<wi;O+=1)for(let Q=0;Q<Si;Q+=1){const nt=Sl(G,Q,O),rt=wl(nt),[ht,ot]=yl(Q,O);if(rt){const W=xl[nt]??"corridor",J=vl[W];let it=p.get(I+":"+W);it||(it={deck:I,cells:[],minCol:Q,maxCol:Q,minRow:O,maxRow:O},p.set(I+":"+W,it)),it.cells.push([Q,O]),it.minCol=Math.min(it.minCol,Q),it.maxCol=Math.max(it.maxCol,Q),it.minRow=Math.min(it.minRow,O),it.maxRow=Math.max(it.maxRow,O),m.has(I+":"+Q+":"+O)||(l.push(Yt(Mt,.2,Mt,ht,F-.1,ot)),c.push(Yt(Mt,.2,Mt,ht,F+zt+.1,ot)),t.add(new R(ht-Mt/2,F-.2,ot-Mt/2),new R(ht+Mt/2,F,ot+Mt/2),"floor"),t.add(new R(ht-Mt/2,F+zt,ot-Mt/2),new R(ht+Mt/2,F+zt+.2,ot+Mt/2),"ceiling")),(Q+O)%2===0&&u.push(Yt(Mt*.5,.06,.28,ht,F+zt-.08,ot));const pt=[{dc:-1,dr:0,axis:"x",sign:-1},{dc:1,dr:0,axis:"x",sign:1},{dc:0,dr:-1,axis:"z",sign:-1},{dc:0,dr:1,axis:"z",sign:1}];for(const mt of pt){const Tt=Q+mt.dc,kt=O+mt.dr,Kt=Sl(G,Tt,kt),Bt=wl(Kt),C=Bt?xl[Kt]??"":"";if(Bt&&C===W)continue;const ye=(mt.axis==="x",Mt),Ut=.18,Gt=Mt/2,ut=mt.axis==="x"?ht+mt.sign*Gt:ht,At=mt.axis==="z"?ot+mt.sign*Gt:ot,bt=mt.axis==="x"?Ut:ye,b=mt.axis==="z"?Ut:ye,M=Bt,B=!Bt&&J?.windows===!0&&Vr(Tt,kt);if(M){const Y=(Mt-Rn)/2,Z=zt-ze,j=(Rn+Y)/2;mt.axis==="x"?(_i(h,t,bt,zt,Y,ut,F+zt/2,ot-j),_i(h,t,bt,zt,Y,ut,F+zt/2,ot+j),_i(h,t,bt,Z,Mt,ut,F+ze+Z/2,ot)):(_i(h,t,Y,zt,b,ht-j,F+zt/2,At),_i(h,t,Y,zt,b,ht+j,F+zt/2,At),_i(h,t,Mt,Z,b,ht,F+ze+Z/2,At)),mt.axis==="x"?(u.push(Yt(Ut*1.6,ze,.08,ut,F+ze/2,ot-Rn/2)),u.push(Yt(Ut*1.6,ze,.08,ut,F+ze/2,ot+Rn/2)),u.push(Yt(Ut*1.6,.08,Rn,ut,F+ze,ot))):(u.push(Yt(.08,ze,Ut*1.6,ht-Rn/2,F+ze/2,At)),u.push(Yt(.08,ze,Ut*1.6,ht+Rn/2,F+ze/2,At)),u.push(Yt(Rn,.08,Ut*1.6,ht,F+ze,At)));continue}if(B){const Y=Gn,Z=zt-He;mt.axis==="x"?(h.push(Yt(bt,Y,Mt,ut,F+Y/2,ot)),h.push(Yt(bt,Z,Mt,ut,F+He+Z/2,ot)),f.push(Yt(.06,He-Gn,Mt*.98,ut,F+(Gn+He)/2,ot))):(h.push(Yt(Mt,Y,b,ht,F+Y/2,At)),h.push(Yt(Mt,Z,b,ht,F+He+Z/2,At)),f.push(Yt(Mt*.98,He-Gn,.06,ht,F+(Gn+He)/2,At))),mt.axis==="x"?(u.push(Yt(.12,.08,Mt,ut,F+Gn,ot)),u.push(Yt(.12,.08,Mt,ut,F+He,ot))):(u.push(Yt(Mt,.08,.12,ht,F+Gn,At)),u.push(Yt(Mt,.08,.12,ht,F+He,At))),t.add(mt.axis==="x"?new R(ut-.12,F,ot-Mt/2):new R(ht-Mt/2,F,At-.12),mt.axis==="x"?new R(ut+.12,F+Y,ot+Mt/2):new R(ht+Mt/2,F+Y,At+.12),"wall"),t.add(mt.axis==="x"?new R(ut-.12,F+He,ot-Mt/2):new R(ht-Mt/2,F+He,At-.12),mt.axis==="x"?new R(ut+.12,F+zt,ot+Mt/2):new R(ht+Mt/2,F+zt,At+.12),"wall"),t.add(mt.axis==="x"?new R(ut-.12,F+Y,ot-Mt/2):new R(ht-Mt/2,F+Y,At-.12),mt.axis==="x"?new R(ut+.12,F+He,ot+Mt/2):new R(ht+Mt/2,F+He,At+.12),"glass");continue}h.push(Yt(bt,zt,b,ut,F+zt/2,At)),t.add(new R(ut-bt/2,F,At-b/2),new R(ut+bt/2,F+zt,At+b/2),"wall"),J&&J.windows&&Vr(Tt,kt)&&d.push(Yt(mt.axis==="x"?.22:Mt*.6,.16,mt.axis==="z"?.22:Mt*.6,ut,F+zt-.4,At))}}else Vr(Q,O)&&(Q===0&&g.push(Yt(.6,16,Mt,Xn(0)-.6/2+.2,F+zt/2,ot)),Q===Si-1&&g.push(Yt(.6,16,Mt,Xn(Si-1)+Mt+.6/2-.2,F+zt/2,ot)),O===0&&g.push(Yt(Mt,16,.6,ht,F+zt/2,Yn(0)-.6/2+.2)),O===wi-1&&g.push(Yt(Mt,16,.6,ht,F+zt/2,Yn(wi-1)+Mt+.6/2-.2)),I===0&&g.push(Yt(Mt,.6,Mt,ht,F-.6,ot)),I===ke.length-1&&g.push(Yt(Mt,.6,Mt,ht,F+zt+.9,ot)))}});const y=Xn(0)-1,_=Xn(Si-1)+Mt+1,S=Yn(0)-1,P=Yn(wi-1)+Mt+1,T=-3,A=ke[ke.length-1].y+zt+2.2;g.push(Yt(10,A-T,P-S,_-5,(T+A)/2,(S+P)/2)),g.push(Yt(12,(A-T)*.36,P-S,y-6,(T+A)/2,(S+P)/2));for(const G of[-1,1]){const I=G>0?P+.6:S-.6;for(let F=0;F<9;F+=1){const O=y+8+F*((_-y-16)/9);v.push(Yt(3.4,.5,.3,O,es[1]+zt-1.2,I)),v.push(Yt(3.4,.5,.3,O,es[2]+zt-1.2,I))}}for(const G of[-9,0,9]){const I=new Jn(2.6,3.4,4,18,1,!0);I.rotateZ(Math.PI/2),I.translate(y-11,3.6,G),u.push(I)}g.push(Yt(14,6,16,_+5,A-7,0)),e?.("正在装配舱室设备…");const L=(G,I,F)=>{if(G.length===0)return;const O=uc(G,!1);for(const nt of G)nt.dispose();if(!O)return;const Q=new Ct(O,I);Q.name=F,Q.matrixAutoUpdate=!1,Q.frustumCulled=!1,n.add(Q)};L(l,s.floor,"floors"),L(h,s.wall,"walls"),L(d,s.wallAccent,"wall-accent"),L(c,s.ceiling,"ceilings"),L(u,s.trim,"trim"),L(f,s.glass,"glass"),L(g,s.hull,"hull"),L(v,s.emissive,"hull-windows");for(const G of Ml){const[I,F]=yl(G.col,G.row),O=ke[G.fromDeck].y,Q=ke[G.toDeck].y,nt=Q-O,rt=new Ze,ht=new Te(.12,nt,.12);for(const W of[-.35,.35]){const J=new Ct(ht,s.prop);J.position.set(I-1.6,O+nt/2,F+W),rt.add(J)}for(let W=0;W<Math.floor(nt/.36);W+=1){const J=new Ct(new Te(.1,.06,.8),s.prop);J.position.set(I-1.6,O+.3+W*.36,F),rt.add(J)}const ot=new Ct(new ti(1.1,.06,6,24),s.trim);ot.rotation.x=Math.PI/2,ot.position.set(I,Q+.05,F),rt.add(ot),n.add(rt),o.push({min:new R(I-1.6,O,F-1.2),max:new R(I+.2,Q+.6,F+1.2)})}for(const[G,I]of p){const F=G.split(":")[1],O=vl[F],Q=Xn(I.minCol),nt=Xn(I.maxCol)+Mt,rt=Yn(I.minRow),ht=Yn(I.maxRow)+Mt,ot=ke[I.deck].y;if(r.push({id:F,label:O?.label||F,description:O?.description||"",deck:I.deck,min:new R(Q,ot,rt),max:new R(nt,ot+zt,ht)}),F!=="corridor"&&O){const W=new Ct(new Qn(3.2,1),new fe({map:hc(O.label,I.deck===0?"下层甲板":I.deck===1?"主甲板":"上层甲板"),transparent:!0,side:de})),J=(Q+nt)/2,it=rt+.25;W.position.set(J,ot+zt-.75,it),W.rotation.y=Math.PI,n.add(W)}}for(const G of X0){const I=r.find(rt=>rt.id===G.room);if(!I)continue;const F=(I.min.x+I.max.x)/2,O=(I.min.z+I.max.z)/2,Q=(rt,ht,ot)=>Math.min(Math.max(rt,ht),ot),nt=new R(Q(F+G.offset[0],I.min.x+1.4,I.max.x-1.4),I.min.y,Q(O+G.offset[1],I.min.z+1.4,I.max.z-1.4));a.set(G.id,{spec:G,position:nt,yaw:G.yaw,roomLabel:I.label,deck:I.deck})}const q=r.find(G=>G.id==="bridge")||r[0],x=new R((q.min.x+q.max.x)/2+4,q.min.y+.1,(q.min.z+q.max.z)/2),E=new cc(8231352,1.15),z=new Zm(12575999,2830908,.85);n.add(E,z);const V=[[x.x,q.min.y+2.4,x.z,13627135,1.5],[-30,ke[0].y+2.4,0,10476799,1.3],[30,ke[0].y+2.4,0,10476799,1.3],[-34,ke[1].y+2.4,0,13627135,1.3],[10,ke[1].y+2.4,0,10476799,1.3],[-40,ke[2].y+2.4,16,11520255,1.2],[10,ke[2].y+2.4,12,11520255,1.2]];for(const[G,I,F,O,Q]of V){const nt=new Jm(O,Q,46,1.4);nt.position.set(G,I,F),n.add(nt)}i.add(n);const K=new Un(new R(y-12,T,S-1),new R(_+12,A,P+1));return{group:n,materials:s,rooms:r,anchors:a,ladders:o,spawn:x,spawnYaw:Math.PI/2,hullBounds:K,dispose(){i.remove(n),n.traverse(G=>{const I=G;I.geometry&&I.geometry.dispose()})}}}function q0(i,t){for(const e of i)if(t.x>=e.min.x-.4&&t.x<=e.max.x+.4&&t.z>=e.min.z-.4&&t.z<=e.max.z+.4&&Math.abs(t.y-e.min.y)<3)return e;return null}function K0(i){let t=i>>>0;return()=>(t=t*1664525+1013904223>>>0,t/4294967296)}function Ae(i,t,e=0){const n=new Te(i[0],i[1],i[2]);return e&&n.rotateY(e),n.translate(t[0],t[1],t[2]),n}function j0(i,t,e,n){const s=new Ze;s.name="ship-props";const r=[],a=[],o=[],l=(c,u,f,g=0,v=!0)=>{if(c.push(Ae(u,f,g)),v){const m=new R(u[0]/2,u[1]/2,u[2]/2);if(g){const y=Math.max(m.x,m.z);m.set(y,m.y,y)}const p=new R(f[0],f[1],f[2]);t.add(p.clone().sub(m),p.clone().add(m),"prop")}};let h=7;for(const c of n){const u=K0(h+=977),f=c.max.x-c.min.x,g=c.max.z-c.min.z,v=c.min.y,m=(c.min.x+c.max.x)/2,p=(c.min.z+c.max.z)/2,y=Math.max(2,Math.floor(f/8));for(let _=0;_<y;_+=1){const S=c.min.x+(_+.5)/y*f;l(r,[.5,.35,g*.92],[S,v+zt-.22,p],0,!1)}if(o.push(Ae([f*.94,.08,.06],[m,v+.12,c.min.z+.22])),o.push(Ae([f*.94,.08,.06],[m,v+.12,c.max.z-.22])),c.id==="corridor"){const _=Math.floor(f/10);for(let S=0;S<_;S+=1){const P=c.min.x+(S+.5)/_*f;for(const T of[-1,1])l(r,[.4,zt,.4],[P,v+zt/2,p+T*(g/2-.5)]),o.push(Ae([.16,1.4,.16],[P,v+1.9,p+T*(g/2-.5)]))}continue}if(c.id==="bridge"){for(let _=0;_<5;_+=1){const S=-.9+_*.45,P=m+12+Math.cos(S)*5,T=p+Math.sin(S)*5;l(a,[.9,.5,.9],[P,v+.25,T]),l(a,[.9,1.1,.2],[P,v+.85,T+Math.sin(S)*.4])}l(a,[1.4,.6,1.4],[m+13,v+.3,p]),l(a,[1.4,1.2,.3],[m+13.7,v+1,p]),o.push(Ae([1.2,.08,1.2],[m+13,v+.62,p]))}else if(c.id==="engineering"){for(let _=0;_<4;_+=1){const S=c.min.x+4+_*(f/4.4);l(a,[1.6,zt,1.6],[S,v+zt/2,p-g*.28]),o.push(Ae([1.7,.2,1.7],[S,v+1.2,p-g*.28])),o.push(Ae([1.7,.2,1.7],[S,v+2.4,p-g*.28]))}for(let _=0;_<6;_+=1){const S=c.min.x+2+_*(f/6.5);l(a,[.6,.6,g*.9],[S,v+zt-.9,p],0,!1)}}else if(c.id==="hangar"){for(let _=0;_<8;_+=1){const S=c.min.x+3+u()*(f-6),P=c.min.z+3+u()*(g-6),T=1.2+u()*1.4;l(a,[T,T,T],[S,v+T/2,P],u()*.6)}l(a,[6,.4,3],[m,v+3.2,p-g*.3],0,!1),o.push(Ae([5.6,.1,2.6],[m,v+3.42,p-g*.3]))}else if(c.id==="cargo")for(let _=0;_<14;_+=1){const S=c.min.x+2+u()*(f-4),P=c.min.z+2+u()*(g-4),T=1+u()*1.3,A=1+Math.floor(u()*2);for(let L=0;L<A;L+=1)l(a,[T,T*.8,T],[S,v+T*.4+L*T*.85,P],u()*.9)}else if(c.id==="lounge"){for(let _=0;_<4;_+=1){const S=c.min.x+4+_*(f/4.6);l(a,[1.8,.45,1.8],[S,v+.22,p+g*.18]),l(a,[1.8,.9,.3],[S,v+.65,p+g*.18+.75]),l(a,[.5,.6,.9],[S-.9,v+.7,p+g*.1])}for(let _=0;_<3;_+=1){const S=c.min.x+3+_*(f/3.4);l(a,[.7,.7,.7],[S,v+.35,p-g*.3]),o.push(Ae([.5,.6,.5],[S,v+1,p-g*.3]))}}else if(c.id==="medbay"){for(let _=0;_<3;_+=1){const S=c.min.z+4+_*(g/3.4);l(a,[2.4,.6,1.1],[m-2,v+.3,S]),l(a,[.4,.9,1.1],[m-3.3,v+.45,S])}o.push(Ae([f*.5,.16,.16],[m,v+zt-.6,p]))}else if(c.id==="science"){for(let _=0;_<5;_+=1){const S=c.min.x+3+_*(f/5.5);l(a,[1.6,.9,1.2],[S,v+.45,p+g*.22]),o.push(Ae([1.4,.06,1],[S,v+.94,p+g*.22]))}for(let _=0;_<3;_+=1){const S=c.min.z+3+_*(g/3.2);l(a,[.8,2.4,.8],[m-8,v+1.2,S]),o.push(Ae([.9,.12,.9],[m-8,v+2,S]))}}else if(c.id==="archive")for(let _=0;_<8;_+=1){const S=_%2===0?-1:1,P=c.min.x+3+Math.floor(_/2)*6,T=p+S*(g*.3);l(a,[3.6,2.6,.7],[P,v+1.3,T]),o.push(Ae([3.2,.06,.08],[P,v+1.6,T+S*.4]))}else if(c.id==="command"){l(a,[6,.35,2.4],[m,v+1.05,p]);for(let _=0;_<5;_+=1){const S=m-2.4+_*1.2;l(a,[.9,.5,.9],[S,v+.25,p+1.8]),l(a,[.9,1,.2],[S,v+.8,p+2.2])}o.push(Ae([5.6,.06,2],[m,v+1.24,p]))}else if(c.id==="observation"){for(let _=0;_<6;_+=1){const S=c.min.x+5+_*(f/6.4);l(a,[3,.45,1],[S,v+.22,p-g*.3]),l(a,[3,.8,.25],[S,v+.6,p-g*.3-.4])}for(let _=0;_<4;_+=1){const S=c.min.x+8+_*(f/4.4);o.push(Ae([.5,3.2,.5],[S,v+1.6,p+g*.34]))}}}const d=(c,u,f)=>{if(c.length===0)return;const g=uc(c,!1);for(const m of c)m.dispose();if(!g)return;const v=new Ct(g,u);v.name=f,v.matrixAutoUpdate=!1,v.frustumCulled=!1,s.add(v)};return d(r,e.ceiling,"prop-panels"),d(a,e.prop,"prop-metal"),d(o,e.trim,"prop-glow"),i.add(s),s}function ns(i,t=2){return String(i).padStart(t,"0")}function Ui(i){if(i==null||!Number.isFinite(i)||i<=0)return"—";const t=Math.floor(i),e=Math.floor(t/86400),n=Math.floor(t%86400/3600),s=Math.floor(t%3600/60),r=t%60;return e>0?e+" 天 "+n+" 小时":n>0?n+" 小时 "+ns(s)+" 分":s>0?s+" 分 "+ns(r)+" 秒":r+" 秒"}function pe(i){return i==null||!Number.isFinite(i)?"—":Math.round(i).toLocaleString("zh-CN")}function is(i){return i==null||!Number.isFinite(i)?"—":i>=1e6?(i/1e6).toFixed(2)+"M":i>=1e3?(i/1e3).toFixed(1)+"K":String(Math.round(i))}function qs(i){return i==null||!Number.isFinite(i)?"—":i===0?"¥0":i<.01?"¥"+i.toFixed(4):i<1?"¥"+i.toFixed(3):"¥"+i.toFixed(2)}function Z0(i){if(!i)return"—";const t=new Date(i);return Number.isNaN(t.getTime())?String(i).slice(11,19)||"—":ns(t.getHours())+":"+ns(t.getMinutes())+":"+ns(t.getSeconds())}function tr(i){return i.status===401?"面板会话已失效，请回到控制台重新登录":i.error||"请求失败"}function sn(){return{value:null,error:null,updatedAt:0}}const $0={id:"dashboard",title:"主控台",subtitle:"舰船总览 · MASTER CONSOLE",accent:3725567,create(i){const t=sn(),e=sn(),n=sn(),s=sn(),r=sn();let a=!1;const o=[new re(()=>i.host.consoleApi.get("/api/overview"),5e3,h=>{t.value=h,t.updatedAt=performance.now(),i.redraw()},h=>{t.error=h,i.redraw()}),new re(()=>i.host.consoleApi.get("/api/series/latency"),8e3,h=>{e.value=h,i.redraw()}),new re(()=>i.host.consoleApi.get("/api/series/messages?days=14"),3e4,h=>{n.value=h,i.redraw()}),new re(()=>i.host.consoleApi.get("/api/stats/usage?hours=24"),3e4,h=>{s.value=h,i.redraw()}),new re(()=>i.host.consoleApi.get("/api/plugins"),2e4,h=>{typeof h.manage_enabled=="boolean"&&i.shell.setManageEnabled(h.manage_enabled),i.redraw()}),new re(()=>i.host.consoleApi.get("/api/admin/power"),5e3,h=>{r.value=h,i.redraw()})];async function l(h,d,c){a=!0,i.redraw();const u=await i.host.consoleApi.post(h,d);if(a=!1,u.ok){i.toast(c,"ok");for(const f of o)f.tick()}else i.toast(tr(u),"error");i.redraw()}return{pollers:o,onFocus(){i.redraw()},draw(h,d){const c=i.shell.status,u=t.value||{},g=!!((r.value||{}).standby??c.standby);h.panel({x:20,y:130,w:330,h:250},{title:"舰体状态 / HULL"});const v=g?.32:J0(1-(c.plugins.error||0)*.08);h.gauge({x:110,y:300},62,v,{valueText:(v*100).toFixed(0)+"%",label:g?"低功耗":"运转正常",color:g?h.theme.warn:h.theme.ok}),h.keyValue(190,220,150,"运行时长",Ui(u.uptime_seconds??c.uptime_seconds)),h.keyValue(190,248,150,"在位插件",String(c.plugins.running)+"/"+String(c.plugins.total)),h.keyValue(190,276,150,"待机时长",g?Ui(c.standby_seconds):"—"),h.keyValue(190,304,150,"OneBot",c.online?"已连接":"未连接",c.online?h.theme.ok:h.theme.error),h.keyValue(190,332,150,"版本",String(u.app_version||"—")),h.panel({x:368,y:130,w:636,h:250},{title:"实时指标 / TELEMETRY"});const m=(e.value?.series||[]).map(_=>Number(_.ms||0));h.sparkline({x:388,y:190,w:300,h:84},m.slice(-60),{label:"API 往返延迟",valueText:String(Math.round(e.value?.current_ms??0))+" ms",fill:!0});const p=(n.value?.series||[]).map(_=>Number(_.count||0));h.sparkline({x:706,y:190,w:278,h:84},p.slice(-40),{label:"近 14 天消息量",valueText:pe(u.today_messages)+" / 今日",fill:!0,color:h.theme.ok}),h.keyValue(388,300,280,"今日消息",pe(u.today_messages)),h.keyValue(388,326,280,"累计消息",pe(u.total_messages)),h.keyValue(388,352,280,"模型调用（24h）",pe(s.value?.totals?.calls)),h.keyValue(706,300,278,"24h 消耗",qs(s.value?.totals?.cost_cny)),h.keyValue(706,326,278,"输入 / 输出",is(s.value?.totals?.input_tokens)+" / "+is(s.value?.totals?.output_tokens)),h.keyValue(706,352,278,"在线机器人",String(u.bot_nickname||"—")),h.panel({x:20,y:396,w:984,h:158},{title:"舰船指令 / COMMAND",tone:h.theme.warn}),h.text(40,448,g?"舰船当前处于低功耗待机：仅主控台、配置、日志与插件终端在线。":"所有系统在线。危险指令会有二次确认。",{size:17,color:g?h.theme.warn:h.theme.textDim});const y=!a&&g;h.button("power-resume",{x:40,y:468,w:190,h:58},a?"执行中…":"恢复运行",{disabled:!y,tone:h.theme.ok})&&(async()=>await i.confirm({title:"恢复舰船运行",body:"将重建 bot 运行时（回复、记忆、Agent 全部恢复）。期间消息处理会短暂中断。",confirmLabel:"恢复运行"})&&await l("/api/admin/resume",{reason:"星舰主控台恢复"},"已开始恢复运行"))(),h.button("power-standby",{x:246,y:468,w:190,h:58},"进入待机",{disabled:a||g,tone:h.theme.warn})&&(async()=>await i.confirm({title:"进入待机（低功耗）",body:"将停止回复与记忆管线，只保留面板与核心服务。舰内多数终端会随之离线。",confirmLabel:"进入待机",danger:!0})&&await l("/api/admin/standby",{reason:"星舰主控台待机"},"已进入待机"))(),h.button("power-reboot",{x:452,y:468,w:190,h:58},"软重启运行",{disabled:a,tone:h.theme.warn})&&(async()=>await i.confirm({title:"软重启运行",body:"重建运行时并按当前配置重新装配（不重启进程）。",confirmLabel:"软重启",danger:!0})&&await l("/api/admin/reboot",{reason:"星舰主控台软重启"},"已开始软重启"))(),h.button("admin-restart",{x:658,y:468,w:190,h:58},"重启 NeoBot",{disabled:a,tone:h.theme.error})&&(async()=>await i.confirm({title:"重启 NeoBot 进程",body:"整个进程会退出并重新启动，网页面板会短暂断开（本页面随后需要刷新）。",confirmLabel:"确认重启",danger:!0})&&await l("/api/admin/restart",{},"重启指令已下发"))(),h.button("open-console",{x:854,y:562,w:130,h:30},"在面板中打开",{size:15,tone:h.theme.textDim})&&window.open(new URL("../",window.location.href).toString(),"_blank"),d||h.text(40,545,"靠近并按 E 可操作终端",{size:15,color:h.theme.textDim})}}}};function J0(i){return Math.max(0,Math.min(1,i))}const Q0={id:"bots",title:"通讯台",subtitle:"机器人 · 会话 · COMMS",accent:6480072,create(i){const t=sn(),e=sn(),n=sn(),s=sn();return{pollers:[new re(()=>i.host.consoleApi.get("/api/bots"),1e4,a=>{t.value=a,i.redraw()},a=>{t.error=a,i.redraw()}),new re(()=>i.host.consoleApi.get("/api/series/latency"),1e4,a=>{e.value=a,i.redraw()}),new re(()=>i.host.consoleApi.get("/api/stats/active-users?limit=8"),3e4,a=>{n.value=a,i.redraw()}),new re(()=>i.host.consoleApi.get("/api/stats/api-calls?limit=8"),15e3,a=>{s.value=a,i.redraw()})],draw(a){const o=(t.value||[])[0]||{},l=!!o.online;a.panel({x:20,y:130,w:470,h:420},{title:"链路状态 / LINK"}),a.text(44,190,l?"● 通讯链路正常":"○ 未检测到 OneBot 连接",{size:24,color:l?a.theme.ok:a.theme.error}),a.keyValue(44,240,420,"昵称",String(o.nickname||o.name||"—")),a.keyValue(44,272,420,"账号",String(o.user_id||"—")),a.keyValue(44,304,420,"平台",String(o.platform||o.app_name||"—")),a.keyValue(44,336,420,"延迟",String(Math.round(Number(e.value?.current_ms??o.latency_ms??0)))+" ms"),a.keyValue(44,368,420,"成功率",String(Math.round(Number(e.value?.success_rate??100)))+"%"),a.keyValue(44,400,420,"今日消息",pe(Number(o.today_messages??0))),a.keyValue(44,432,420,"累计消息",pe(Number(o.total_messages??0))),a.keyValue(44,464,420,"在线时长",Ui(Number(o.uptime_seconds??0))),a.sparkline({x:44,y:486,w:420,h:44},(e.value?.series||[]).map(c=>Number(c.ms||0)).slice(-60),{color:a.theme.ok,fill:!0}),a.panel({x:508,y:130,w:496,h:200},{title:"活跃会话 / ACTIVE"});const h=(n.value?.items||[]).slice(0,5);h.length===0&&a.text(532,196,"暂无活跃用户数据",{size:17,color:a.theme.textDim}),h.forEach((c,u)=>{a.keyValue(532,186+u*28,448,String(u+1)+". "+String(c.nickname||c.name||c.user_id||"未知"),pe(Number(c.count??c.value??0)))}),a.panel({x:508,y:348,w:496,h:202},{title:"接口调用排行 / API"});const d=(s.value?.items||[]).slice(0,5);d.length===0&&a.text(532,412,"暂无接口调用记录",{size:17,color:a.theme.textDim}),d.forEach((c,u)=>{a.keyValue(532,404+u*28,448,String(u+1)+". "+String(c.name||c.label||"—"),pe(Number(c.count??c.value??0)))})}}}},tg={id:"scores",title:"战绩墙",subtitle:"排行榜 · 成就 · RECORDS",accent:13148927,create(i){const t=sn(),e=sn();let n="";const s=[new re(()=>i.host.gameApi.get("/api/scores?limit=12"+(n?"&game="+encodeURIComponent(n):"")),15e3,r=>{t.value=r,i.redraw()},r=>{t.error=r,i.redraw()}),new re(()=>i.host.gameApi.get("/api/achievements"),3e4,r=>{e.value=r,i.redraw()})];return{pollers:s,draw(r){r.panel({x:20,y:130,w:560,h:424},{title:"排行榜 / LEADERBOARD"}),[["","全部"],["turret","舱外炮塔"],["repair","损管抢修"]].forEach((h,d)=>{r.button("tab-"+d,{x:40+d*118,y:168,w:110,h:36},h[1],{tone:n===h[0]?r.theme.accent:r.theme.textDim,size:16})&&(n=h[0],s[0].tick())});const o=t.value?.items||[];o.length===0&&r.text(44,260,"还没有成绩记录：去机库玩一局吧。",{size:19,color:r.theme.textDim}),o.slice(0,9).forEach((h,d)=>{const c=228+d*36;r.text(44,c,eg(d+1),{size:18,color:d<3?r.theme.warn:r.theme.textDim}),r.text(92,c,String(h.player||"舰长"),{size:18}),r.text(300,c,h.game==="repair"?"损管抢修":"舱外炮塔",{size:16,color:r.theme.textDim}),r.text(544,c,pe(h.score),{size:19,align:"right",color:r.theme.accent})}),r.panel({x:600,y:130,w:404,h:424},{title:"成就 / ACHIEVEMENTS"});const l=e.value?.items||[];l.length===0&&(r.text(624,200,"尚未解锁任何成就。",{size:17,color:r.theme.textDim}),r.text(624,230,"试试：首次跃迁、击毁小行星、完成抢修。",{size:15,color:r.theme.textDim})),l.slice(0,10).forEach((h,d)=>{const c=186+d*36;r.text(624,c,"◈ "+String(h.key||""),{size:17,color:r.theme.accent}),r.text(984,c,"×"+String(h.count??1),{size:16,align:"right",color:r.theme.textDim})})}}}};function eg(i){return String(i).padStart(2,"0")}const ng=[$0,Q0,tg],ig={id:"system",title:"反应堆监控",subtitle:"系统资源 · REACTOR",accent:16757844,decorate(i,t){const e=new Ct(new cs(.45,1),new fe({color:16757844,transparent:!0,opacity:.85}));e.position.set(0,2.4,-.9),i.add(e);const n=new Ct(new ti(.62,.03,6,32),t.trim);n.position.set(0,2.4,-.9),i.add(n)},create(i){let t=null,e=null,n=null,s=null;const r=[];return{pollers:[new re(()=>i.host.consoleApi.get("/api/system"),3e3,o=>{t=o,r.push(Number(o.cpu_percent||0)),r.length>120&&r.shift(),i.redraw()},o=>{s=o,i.redraw()}),new re(()=>i.host.consoleApi.get("/api/tasks"),15e3,o=>{e=o,i.redraw()}),new re(()=>i.host.consoleApi.get("/api/services"),3e4,o=>{n=o,i.redraw()})],draw(o){const l=t||{};o.panel({x:20,y:130,w:640,h:300},{title:"堆芯负载 / CORE LOAD"});const h=Number(l.cpu_percent||0),d=Number(l.mem_percent||0),c=Number(l.disk_percent||0);o.gauge({x:130,y:280},66,h/100,{valueText:h.toFixed(0)+"%",label:"CPU"+(l.cpu_count?" × "+l.cpu_count:""),color:h>85?o.theme.error:o.theme.accent}),o.gauge({x:340,y:280},66,d/100,{valueText:d.toFixed(0)+"%",label:"内存",color:d>90?o.theme.error:o.theme.ok}),o.gauge({x:550,y:280},66,c/100,{valueText:c.toFixed(0)+"%",label:"存储",color:c>92?o.theme.error:o.theme.warn}),o.keyValue(40,380,300,"进程内存",pe(l.process_memory_mb)+" MB"),o.keyValue(360,380,280,"线程数",pe(l.process_threads)),o.keyValue(40,408,300,"内存明细",pe(l.mem_used_mb)+" / "+pe(l.mem_total_mb)+" MB"),o.keyValue(360,408,280,"磁盘占用",(l.disk_used_gb??0).toFixed(1)+" / "+(l.disk_total_gb??0).toFixed(1)+" GB"),o.panel({x:676,y:130,w:328,h:300},{title:"运行信息 / HOST"}),o.keyValue(696,180,288,"主机",String(l.hostname||"—")),o.keyValue(696,208,288,"系统",String(l.os||"—")),o.keyValue(696,236,288,"Python",String(l.python_version||"—")),o.keyValue(696,264,288,"进程 PID",String(l.pid??"—")),o.keyValue(696,292,288,"NeoBot 运行",Ui(i.shell.status.uptime_seconds)),o.keyValue(696,320,288,"负载",(l.load_average||[]).map(v=>v.toFixed(2)).join(" / ")||"—"),o.sparkline({x:696,y:350,w:288,h:60},r.slice(-80),{label:"CPU 曲线",fill:!0}),o.panel({x:20,y:446,w:484,h:108},{title:"后台任务 / TASKS"});const u=e?.scheduled||[],f=e?.background||[];o.keyValue(40,492,444,"定时任务",String(u.length)+" 项"),o.keyValue(40,522,444,"后台作业",String(f.length)+" 项"),e?.scheduled_error&&o.text(40,546,"⚠ "+e.scheduled_error,{size:14,color:o.theme.warn}),o.panel({x:520,y:446,w:484,h:108},{title:"宿主服务 / SERVICES"});const g=(n?.items||[]).slice(0,3);g.length===0&&o.text(540,500,"服务注册表不可用",{size:16,color:o.theme.textDim}),g.forEach((v,m)=>{o.text(540,494+m*24,(v.available===!1?"○ ":"● ")+String(v.name||""),{size:16,color:v.available===!1?o.theme.warn:o.theme.ok})}),s&&o.text(24,128,"",{size:12})}}}},sg={id:"usage",title:"能量分配",subtitle:"模型用量 · POWER GRID",accent:8184063,create(i){const t=El(),e=El();return{pollers:[new re(()=>i.host.consoleApi.get("/api/stats/usage?hours=24"),2e4,s=>{t.value=s,i.redraw()},s=>{t.error=s,i.redraw()}),new re(()=>i.host.consoleApi.get("/api/series/usage?hours=24&bucket=hour"),3e4,s=>{e.value=s,i.redraw()})],draw(s){const r=t.value?.totals||{},a=e.value?.points||[];s.panel({x:20,y:130,w:984,h:190},{title:"总功率 / TOTALS"}),s.gauge({x:130,y:230},58,Math.min(1,Number(r.calls||0)/200),{valueText:pe(r.calls),label:"调用次数"}),s.gauge({x:330,y:230},58,Math.min(1,Number(r.input_tokens||0)/5e5),{valueText:is(r.input_tokens),label:"输入 Token",color:s.theme.ok}),s.gauge({x:530,y:230},58,Math.min(1,Number(r.output_tokens||0)/2e5),{valueText:is(r.output_tokens),label:"输出 Token",color:s.theme.warn}),s.gauge({x:730,y:230},58,Math.min(1,Number(r.cost_cny||0)/20),{valueText:qs(r.cost_cny),label:"24h 花费",color:"#ff9ad5"}),s.sparkline({x:830,y:170,w:154,h:120},a.map(h=>Number(h.cost_cny||0)),{label:"开销曲线",fill:!0,color:"#ff9ad5"}),s.panel({x:20,y:336,w:484,h:218},{title:"按模块 / MODULES"});const o=(t.value?.items||[]).slice(0,7);o.length===0&&s.text(44,400,t.value?.available===!1?"用量库不可用":"24 小时内没有模型调用",{size:17,color:s.theme.textDim}),o.forEach((h,d)=>{const c=386+d*22;s.text(44,c,String(h.module||"未知模块").slice(0,18),{size:16}),s.text(300,c,pe(h.calls)+" 次",{size:15,color:s.theme.textDim}),s.text(484,c,qs(h.cost_cny),{size:16,align:"right",color:s.theme.accent})}),s.panel({x:520,y:336,w:484,h:218},{title:"按模型 / MODELS"});const l=(e.value?.models||[]).slice(0,7);l.length===0&&s.text(544,400,"暂无模型用量明细",{size:17,color:s.theme.textDim}),l.forEach((h,d)=>{const c=386+d*22,u=String(h.model_name||h.name||h.model||"未知模型");s.text(544,c,u.slice(0,22),{size:16}),s.text(784,c,is(Number(h.total_tokens||0)),{size:15,color:s.theme.textDim}),s.text(984,c,qs(Number(h.cost_cny||0)),{size:16,align:"right",color:s.theme.accent})})}}}},rg={id:"plugins",title:"模块机架",subtitle:"插件装载 · MODULE RACK",accent:9109448,decorate(i,t){for(let e=0;e<4;e+=1){const n=new Ct(new Te(.28,.5,.36),t.prop);n.position.set(-1.1+e*.72,2.3,-.75),i.add(n);const s=new Ct(new Te(.16,.04,.02),t.emissive);s.position.set(-1.1+e*.72,2.5,-.56),i.add(s)}},create(i){let t=null,e=null,n="",s=!1;const r=[new re(()=>i.host.consoleApi.get("/api/plugins"),12e3,o=>{t=o,typeof o.manage_enabled=="boolean"&&i.shell.setManageEnabled(o.manage_enabled),!n&&(o.items||[]).length>0&&(n=String((o.items||[])[0].id||"")),i.redraw()},o=>{e=o,i.redraw()})];async function a(o,l){const h=(t?.items||[]).find(f=>f.id===o),d=h?!h.enabled:!0;if(!await i.confirm({title:l==="toggle"?d?"启用模块 "+o:"停用模块 "+o:"重载模块 "+o,body:l==="toggle"?d?"模块会立即装载并启动。":"模块会立即停止；依赖它的模块会被联动停用（前置插件满足后会自动恢复）。":"模块会重新导入并重启，期间它的功能短暂不可用。",confirmLabel:l==="toggle"?d?"启用":"停用":"重载",danger:l==="toggle"&&!d}))return;s=!0,i.redraw();const u=await i.host.consoleApi.post("/api/plugins/"+encodeURIComponent(o)+"/"+l,{});s=!1,u.ok?i.toast(u.data?.message||"操作完成","ok"):i.toast(tr(u),"error"),r[0].tick(),i.redraw()}return{pollers:r,draw(o){const l=t?.items||[];o.panel({x:20,y:130,w:520,h:424},{title:"模块清单 / MODULES ("+l.length+")"});const h=l.map(u=>({label:u.name+(u.official?" · 官方":""),sub:"v"+String(u.version||"?")+(u.auto_disabled?" · 依赖未满足":"")+(u.dependency_issues&&u.dependency_issues.length>0?" · "+u.dependency_issues[0]:""),badge:u.status==="running"?"运行中":u.enabled===!1?"已停用":u.status||"",tone:u.status==="running"?o.theme.ok:u.auto_disabled?o.theme.warn:u.status==="error"?o.theme.error:o.theme.textDim,active:u.id===n})),d=o.list("plugins",{x:36,y:168,w:488,h:372},h,{rowHeight:46});d>=0&&l[d]&&(n=String(l[d].id||""));const c=l.find(u=>u.id===n)||l[0];if(o.panel({x:556,y:130,w:448,h:424},{title:"模块详情 / DETAIL"}),!c)o.text(580,200,"没有可显示的模块",{size:18,color:o.theme.textDim});else{o.text(580,186,c.name,{size:26,weight:"bold"}),o.text(580,214,c.description||"（无描述）",{size:15,color:o.theme.textDim,maxWidth:400}),o.keyValue(580,252,400,"版本",String(c.version||"—")),o.keyValue(580,276,400,"状态",String(c.status||"—")),o.keyValue(580,300,400,"作者",String(c.author||"—")),o.keyValue(580,324,400,"热重载",c.hot_reload===!1?"不支持":"支持"),c.dependencies&&c.dependencies.length>0&&o.keyValue(580,348,400,"前置插件",c.dependencies.join(", ")),c.dependents&&c.dependents.length>0&&o.keyValue(580,372,400,"被依赖",c.dependents.join(", ")),c.disabled_reason&&o.text(580,402,"⚠ "+c.disabled_reason,{size:14,color:o.theme.warn,maxWidth:400}),c.dependency_issues&&c.dependency_issues.length>0&&o.text(580,424,"未满足："+c.dependency_issues.join("；"),{size:14,color:o.theme.warn,maxWidth:400});const u=i.shell.availability("plugins").readOnly||s;o.button("toggle",{x:580,y:452,w:190,h:52},c.enabled===!1?"装载模块":"停用模块",{disabled:u,tone:c.enabled===!1?o.theme.ok:o.theme.warn})&&a(String(c.id),"toggle"),o.button("reload",{x:786,y:452,w:198,h:52},s?"执行中…":"热重载",{disabled:u||c.official===!0,tone:o.theme.accent})&&a(String(c.id),"reload"),o.text(580,528,"依赖未满足的模块会被自动停用，前置插件恢复后自动装载。",{size:14,color:o.theme.textDim,maxWidth:400})}e&&o.text(24,120,"⚠ "+e,{size:15,color:o.theme.error})}}}};function El(){return{value:null,error:null,updatedAt:0}}const ag=[ig,sg,rg],og={id:"logs",title:"航行日志",subtitle:"实时日志 · SHIP LOG",accent:10474751,create(i){let t=[],e=null,n="ALL";const s=["ALL","INFO","WARNING","ERROR","DEBUG"];let r=!0;return{pollers:[new re(()=>i.host.consoleApi.get("/api/logs?limit=120"),4e3,o=>{t=o.items||[],i.redraw()},o=>{e=o,i.redraw()})],draw(o){o.panel({x:20,y:130,w:984,h:424},{title:"日志流 / STREAM"}),s.forEach((c,u)=>{o.button("lv-"+c,{x:40+u*96,y:164,w:88,h:32},c,{tone:n===c?o.theme.accent:o.theme.textDim,size:15})&&(n=c,o.scrollReset("logs"))}),o.button("follow",{x:856,y:164,w:128,h:32},r?"自动滚动：开":"自动滚动：关",{tone:r?o.theme.ok:o.theme.textDim,size:15})&&(r=!r);const l=t.filter(c=>n==="ALL"?!0:String(c.level||"").toUpperCase().startsWith(n.slice(0,4))),h=l.slice().reverse().map(c=>({label:"["+Z0(c.time||c.datetime)+"] "+String(c.message||"").slice(0,68),sub:String(c.module||"")+" · "+String(c.level||"").toLowerCase(),tone:String(c.level||"").toUpperCase().startsWith("ERR")?o.theme.error:String(c.level||"").toUpperCase().startsWith("WARN")?o.theme.warn:void 0})),d=o.list("logs",{x:36,y:206,w:952,h:330},h,{rowHeight:40});if(d>=0){const c=l.slice().reverse()[d];c&&i.toast(String(c.module||"")+": "+String(c.message||""),"info")}o.text(24,574,"共 "+String(l.length)+" 条 · 点击条目可在舰桥广播完整内容",{size:14,color:o.theme.textDim}),e&&o.text(700,574,"⚠ "+e,{size:14,color:o.theme.error})}}}},lg={id:"analysis",title:"神经矩阵",subtitle:"提示词分析 · NEURAL MATRIX",accent:16747224,decorate(i){for(let t=0;t<3;t+=1){const e=new Ct(new ti(.5+t*.18,.02,6,40),new fe({color:16747224,transparent:!0,opacity:.5-t*.1}));e.position.set(0,2.5,-.9),e.rotation.x=Math.PI/2+t*.4,i.add(e)}},create(i){let t=null,e=null,n=0;return{pollers:[new re(()=>i.host.consoleApi.get("/api/analysis/prompts"),3e4,r=>{t=r,i.redraw()},r=>{e=r,i.redraw()})],draw(r){const a=cg(t);r.panel({x:20,y:130,w:430,h:424},{title:"分析对象 / SOURCES ("+a.length+")"});const o=a.map(d=>({label:String(d.name||d.label||d.key||d.agent||"未命名"),sub:"约 "+String(Math.round(Number(d.tokens??d.estimated_tokens??0)))+" tokens · "+String(d.chars??0)+" 字符",active:a[n]===d})),l=r.list("analysis",{x:36,y:168,w:398,h:370},o,{rowHeight:44});l>=0&&(n=l),r.panel({x:466,y:130,w:538,h:424},{title:"矩阵详情 / DETAIL"});const h=a[n];if(!h)r.text(490,200,e?"⚠ "+e:"等待分析数据…",{size:18,color:e?r.theme.error:r.theme.textDim});else{r.text(490,190,String(h.name||h.label||h.key||"未命名"),{size:26,weight:"bold"});const d=Number(h.tokens??h.estimated_tokens??0);r.gauge({x:590,y:300},62,Math.min(1,d/8e3),{valueText:Math.round(d)+"",label:"估算 tokens"}),r.keyValue(700,250,284,"字符数",String(h.chars??0)),r.keyValue(700,278,284,"估算 tokens",String(Math.round(d))),r.keyValue(700,306,284,"来源",String(h.agent||h.key||"—"));const c=(h.sections||[]).slice(0,6);c.length===0&&r.text(490,400,"没有分段信息（该来源不提供分段统计）",{size:15,color:r.theme.textDim}),c.forEach((u,f)=>{const g=396+f*24;r.text(490,g,String(u.name||"段落"),{size:15,color:r.theme.textDim}),r.text(960,g,String(Math.round(Number(u.tokens??0)))+" tok",{size:15,align:"right"})}),r.text(490,540,"提示词分析不调用模型，仅统计装配后的字符与估算 token。",{size:14,color:r.theme.textDim,maxWidth:480})}}}}};function cg(i){if(!i)return[];if(Array.isArray(i.items))return i.items;if(Array.isArray(i.sources))return i.sources;const t=[];for(const[e,n]of Object.entries(i))if(n&&typeof n=="object"&&!Array.isArray(n)){const s=n;(typeof s.chars=="number"||typeof s.tokens=="number"||Array.isArray(s.sections))&&t.push({key:e,name:String(s.name||e),...s})}return t}const hg={id:"config",title:"舰载系统配置",subtitle:"本体配置 · SHIP CONFIG",accent:9419007,create(i){let t=null,e=null,n=null,s="",r=!1,a=null;const o=[new re(()=>i.host.consoleApi.get("/api/config"),2e4,c=>{t=c,i.redraw()},c=>{n=c,i.redraw()}),new re(()=>i.host.consoleApi.get("/api/config/env"),3e4,c=>{e=c,i.redraw()})],l=()=>(t?.schema||[]).filter(c=>c.kind==="group");async function h(c,u){if(!t)return;const f=JSON.parse(JSON.stringify(t.config||{}));let g=f;for(let m=0;m<c.length-1;m+=1){const p=c[m],y=g[p];(!y||typeof y!="object")&&(g[p]={}),g=g[p]}g[c[c.length-1]]=u,r=!0,i.redraw();const v=await i.host.consoleApi.post("/api/config",{revision:t.revision,config:f});r=!1,v.ok?(t=v.data||t,i.toast(v.data?.message||"配置已写入 config.toml","ok"),o[0].tick()):i.toast(tr(v),"error"),i.redraw()}function d(c,u){if(u==="bool"||u==="boolean")return c==="true"||c==="是"||c==="1";if(u==="int"||u==="integer")return Number.parseInt(c,10);if(u==="float"||u==="number")return Number.parseFloat(c);const f=c.trim();if(f.startsWith("[")||f.startsWith("{"))try{return JSON.parse(f)}catch{return c}return c}return{pollers:o,draw(c){const u=l();c.panel({x:20,y:130,w:320,h:424},{title:"分区 / SECTIONS ("+u.length+")"});const f=u.map(p=>({label:String(p.name||(p.path||[]).join(".")),sub:String(p.description||"").slice(0,22)||"config.toml",active:s===String(p.name)})),g=c.list("config-sections",{x:36,y:168,w:288,h:370},f,{rowHeight:46});g>=0&&u[g]&&(s=String(u[g].name||""));const v=i.shell.availability("config").readOnly;c.panel({x:356,y:130,w:648,h:424},{title:"参数 / PARAMETERS"});const m=u.find(p=>String(p.name)===s)||u[0];if(!m)c.text(380,200,n?"⚠ "+n:"正在读取 config.toml…",{size:18,color:n?c.theme.error:c.theme.textDim});else{s=String(m.name||"");const p=(m.fields||[]).filter(y=>!y.hidden).slice(0,9);if(c.text(380,176,String(m.name||"")+"  ·  "+String(m.description||""),{size:17,color:c.theme.textDim,maxWidth:600}),p.forEach((y,_)=>{const S=216+_*40;c.isHovered("field-"+_);const P=String(y.name||""),T=y.value,A=T==null?"（未设置）":typeof T=="object"?JSON.stringify(T).slice(0,26):String(T),L={x:380,y:S-20,w:600,h:34};if(c.textField("field-"+_,L,P+"  =  "+A,{placeholder:P,focused:a!==null&&a.path===(y.path||[]).join(".")}).clicked&&!v&&y.kind==="scalar"){const x=y.path||[String(y.name)];a={path:x.join("."),value:T==null?"":String(T)},i.host.textCapture.open({initial:a.value,onType:E=>{a&&(a.value=E),i.redraw()},onCommit:E=>{a=null,h(x,d(E,String(y.type||"")))},onCancel:()=>{a=null,i.redraw()}})}}),c.button("config-reload",{x:380,y:496,w:170,h:44},r?"执行中…":"重载配置",{disabled:r,tone:c.theme.accent,size:16})&&(async()=>{if(!await i.confirm({title:"重载运行配置",body:"按磁盘上的 config.toml 重新装配运行期组件（等价于面板的「重载运行配置」）。",confirmLabel:"重载"}))return;r=!0,i.redraw();const _=await i.host.consoleApi.post("/api/config/reload",{});r=!1,i.toast(_.ok?_.data?.message||"配置已重载":tr(_),_.ok?"ok":"error"),o[0].tick(),i.redraw()})(),c.button("env-open",{x:560,y:496,w:200,h:44},"环境变量密钥",{size:16})){const y=ug(e);i.toast(y.length>0?"已配置 "+y.length+" 个密钥："+y.slice(0,6).join("、")+"（Key 只写不读，需在面板编辑）":"尚未配置任何 API 密钥","info")}v?c.text(380,476,"当前为只读模式：无法保存配置",{size:15,color:c.theme.warn}):c.text(380,552,"点击任意参数行即可修改；保存会写入 config.toml 并做一次校验。",{size:14,color:c.theme.textDim,maxWidth:600})}}}}};function ug(i){if(!i)return[];const e=(i.items||i.entries||[]).map(n=>String(n.key||"")).filter(n=>n.length>0);return e.length>0?e:Array.isArray(i.keys)?i.keys.map(n=>String(n)):[]}const dg=[og,lg,hg],Zi=["天鹅座 λ-4","猎户悬臂 K-17","南门二 β","天苑四 ε","蛇夫座 9","武仙座 τ","船底座 HD-7","仙女座 M31-附","半人马 ζ","天琴座 Vega-2"],fg={id:"navigation",title:"星图导航台",subtitle:"星图 · 跃迁 · NAVIGATION",accent:7327999,decorate(i,t){const e=new Ct(new Pn(.34,20,14),new fe({color:7327999,wireframe:!0,transparent:!0,opacity:.75}));e.position.set(0,2.5,-.7),i.add(e);const n=new Ct(new ti(.5,.012,6,40),t.trim);n.position.set(0,2.5,-.7),n.rotation.x=Math.PI/2.4,i.add(n)},create(i){let t=0,e="";return{idleAnimated:!0,draw(n){const s=i.host.actions,r=s.warping();n.panel({x:20,y:130,w:620,h:424},{title:"星图 / STARCHART"});const a=s.systemName(),o=Zi[(t+1)%Zi.length];n.text(44,200,"当前星系",{size:16,color:n.theme.textDim}),n.text(44,236,a,{size:30,weight:"bold"}),n.text(44,292,"目标星系",{size:16,color:n.theme.textDim}),n.text(44,328,o,{size:30,weight:"bold",color:n.theme.accent});const l=(4.2+t*1.7).toFixed(1);n.keyValue(44,372,560,"航程",l+" 光年"),n.keyValue(44,400,560,"预计跃迁耗时","约 3 秒"),n.keyValue(44,428,560,"引擎状态",r?"跃迁中…":"就绪"),n.button("nav-prev",{x:44,y:456,w:120,h:48},"上一个",{size:17})&&(t=(t+Zi.length-1)%Zi.length),n.button("nav-next",{x:176,y:456,w:120,h:48},"下一个",{size:17})&&(t=(t+1)%Zi.length),n.button("nav-jump",{x:308,y:456,w:220,h:48},r?"跃迁进行中":"启动跃迁",{disabled:r,tone:n.theme.accent})&&s.triggerWarp(!0)&&(e="跃迁引擎已点火："+o,n.scrollReset("nav")),n.text(44,532,e||"跃迁会让全舰进入高速航行状态，舷窗外会变成星流。",{size:15,color:n.theme.textDim,maxWidth:560}),n.panel({x:656,y:130,w:348,h:424},{title:"航道提示 / NOTES"}),n.text(680,200,"· 随机跃迁",{size:17,color:n.theme.accent}),n.text(680,228,"航行一段时间后，舰载 AI 会",{size:15,color:n.theme.textDim}),n.text(680,250,"自动规划一次跃迁。",{size:15,color:n.theme.textDim}),n.text(680,296,"· 手动跃迁",{size:17,color:n.theme.accent}),n.text(680,324,"在本终端选择目标星系并点火。",{size:15,color:n.theme.textDim}),n.text(680,370,"· 观景廊",{size:17,color:n.theme.accent}),n.text(680,398,"跃迁后星云配色与行星都会改变，",{size:15,color:n.theme.textDim}),n.text(680,420,"去观景廊看看新的星系。",{size:15,color:n.theme.textDim});const h=i.host.jumpIntervalMinutes;n.text(680,480,h>0?"自动跃迁间隔：约 "+h+" 分钟":"自动跃迁已关闭",{size:15,color:n.theme.textDim})}}}},pg=[{id:"espresso",name:"双份浓缩",desc:"短时间提升移动速度",boost:"sprint",seconds:45},{id:"cocoa",name:"舰载可可",desc:"暖胃，纯粹好喝",boost:null,seconds:0},{id:"tea",name:"合成红茶",desc:"提升跳跃高度一点点",boost:"jump",seconds:40}],mg={id:"coffee",title:"咖啡机",subtitle:"船员补给 · GALLEY",accent:16764810,create(i){let t=0,e=0;return{draw(n){n.panel({x:20,y:130,w:640,h:424},{title:"菜单 / MENU"}),pg.forEach((a,o)=>{const l=190+o*78,h={x:44,y:l,w:592,h:64},d=n.isHovered("drink-"+o);n.panel(h,{tone:t===o||d?n.theme.accent:n.theme.panelEdge}),n.text(64,l+28,a.name,{size:22,color:n.theme.text}),n.text(64,l+52,a.desc,{size:15,color:n.theme.textDim}),n.button("pour-"+o,{x:500,y:l+12,w:118,h:40},"接一杯",{size:16})&&(t=o,e+=1,i.host.actions.playChime("coffee"),i.toast("接了一杯"+a.name+"，舰桥的空气里都是香味。","ok"),a.boost&&(i.host.actions.boost(a.boost,a.seconds),i.toast("获得增益："+a.desc+"（"+a.seconds+" 秒）","info")),i.host.actions.unlockAchievement("galley-visit","在休息厅接了一杯饮品"))}),n.panel({x:684,y:130,w:320,h:424},{title:"状态 / STATUS"}),n.text(708,200,"今日供应",{size:16,color:n.theme.textDim}),n.text(708,236,String(e)+" 杯",{size:32,weight:"bold",color:n.theme.accent}),n.text(708,300,"增益",{size:16,color:n.theme.textDim});const s=i.host.actions.boostRemaining("sprint"),r=i.host.actions.boostRemaining("jump");n.text(708,336,s>0?"疾跑 +25%（"+s.toFixed(0)+"s）":"无",{size:18}),n.text(708,368,r>0?"跳跃 +15%（"+r.toFixed(0)+"s）":"无",{size:18}),n.text(708,440,"提示：按住 Ctrl 疾跑。",{size:15,color:n.theme.textDim})}}}},bl=[{id:"bridge",name:"舰桥主题",scale:[220,277,330,415,494]},{id:"warp",name:"跃迁回响",scale:[196,233,294,349,392]},{id:"hangar",name:"机库节拍",scale:[262,311,392,466,523]}],gg={id:"jukebox",title:"点唱机",subtitle:"船员娱乐 · JUKEBOX",accent:13214463,create(i){let t=-1,e=0;const n=new Array(18).fill(0);return{idleAnimated:!0,draw(s){const r=t>=0;s.panel({x:20,y:130,w:984,h:424},{title:"曲库 / LIBRARY"}),bl.forEach((a,o)=>{const l=178+o*56;s.text(48,l+24,(t===o?"▶ ":"· ")+a.name,{size:20,color:t===o?s.theme.accent:s.theme.text}),s.button("track-"+o,{x:760,y:l+4,w:110,h:40},t===o?"停止":"播放",{size:16})&&(t===o?(t=-1,i.host.actions.stopMusic()):(t=o,i.host.actions.playMusic(a.scale)))}),e+=1;for(let a=0;a<n.length;a+=1){const o=r?Math.abs(Math.sin(e*.05+a*.7))*(.4+Math.random()*.6):.04;n[a]=n[a]*.7+o*.3}s.panel({x:48,y:360,w:928,h:170},{title:"频谱 / SPECTRUM"}),n.forEach((a,o)=>{const l=Math.max(4,a*120);s.ctx.fillStyle=o%2===0?s.theme.accent:s.theme.ok,s.ctx.fillRect(72+o*50,506-l,30,l)}),s.text(48,546,r?"正在播放："+bl[t].name+"（合成音律，无外部音频文件）":"点「播放」试试，音效由 WebAudio 实时合成。",{size:15,color:s.theme.textDim}),i.host.actions.setMusicActive(r)}}}},_g={id:"vitals",title:"生命体征仪",subtitle:"舰体诊断 · MEDBAY",accent:9109456,create(i){let t=null;const e=[];return{pollers:[new re(()=>i.host.consoleApi.get("/api/system"),3e3,s=>{t=s,e.push(Number(s.cpu_percent||0)),e.length>120&&e.shift(),i.redraw()})],draw(s){const r=t||{};s.panel({x:20,y:130,w:984,h:424},{title:"舰体体征 / VITALS"});const a=.5+.5*Math.sin(performance.now()/380);s.gauge({x:180,y:300},88,Number(r.cpu_percent||0)/100,{valueText:String(Math.round(Number(r.cpu_percent||0)))+"%",label:"神经活动（CPU）",color:s.theme.ok}),s.gauge({x:440,y:300},88,Number(r.mem_percent||0)/100,{valueText:String(Math.round(Number(r.mem_percent||0)))+"%",label:"体液循环（内存）"}),s.gauge({x:700,y:300},88,a,{valueText:"正常",label:"心跳（进程）",color:s.theme.accent}),s.sparkline({x:836,y:240,w:148,h:120},e.slice(-80),{label:"心电图",fill:!0,color:s.theme.ok}),s.keyValue(48,420,400,"舰体运行时长",Ui(i.shell.status.uptime_seconds)),s.keyValue(48,450,400,"进程内存",pe(r.process_memory_mb)+" MB"),s.keyValue(48,480,400,"线程数",pe(r.process_threads)),s.keyValue(520,420,460,"磁盘占用",(r.disk_used_gb??0).toFixed(1)+" / "+(r.disk_total_gb??0).toFixed(1)+" GB"),s.keyValue(520,450,460,"主机",String(r.hostname||"—")),s.keyValue(520,480,460,"系统",String(r.os||"—")),s.text(48,528,"医务室建议：CPU 长期高于 85% 时，考虑减少并发任务。",{size:15,color:s.theme.textDim})}}}},xg={id:"supplies",title:"补给箱",subtitle:"随身物资 · SUPPLIES",accent:16765567,create(i){let t=0;return{draw(e){e.panel({x:20,y:130,w:984,h:424},{title:"物资清单 / INVENTORY"}),e.text(48,200,"已开启补给："+t+" 箱",{size:24}),[["应急口粮",t>0?"×1":"未领取"],["磁力靴保养包",t>1?"×1":"未领取"],["备用氧烛",t>2?"×1":"未领取"]].forEach((s,r)=>{e.keyValue(48,256+r*40,460,s[0],s[1])}),e.button("open-supply",{x:48,y:420,w:220,h:56},"开启补给箱",{tone:e.theme.warn})&&(t+=1,i.host.actions.playChime("supply"),i.toast("补给箱已开启（第 "+t+" 箱）。","ok"),i.host.actions.unlockAchievement("supply-run","开启货舱补给箱"),i.redraw()),e.text(48,512,"补给只是仪式感：真正让这艘船运转的是后排那台服务器。",{size:15,color:e.theme.textDim})}}}},vg={id:"telescope",title:"天文望远镜",subtitle:"舰外观测 · TELESCOPE",accent:11067647,create(i){const t=["主行星","伴星卫星","小行星带","航道上的货船"];let e=0,n=1;return{draw(s){s.panel({x:20,y:130,w:640,h:424},{title:"观测目标 / TARGETS"}),t.forEach((r,a)=>{s.button("target-"+a,{x:44,y:180+a*60,w:360,h:48},r,{tone:e===a?s.theme.accent:s.theme.textDim})&&(e=a,i.host.actions.lookAtTarget(r),i.host.actions.unlockAchievement("stargazer","用望远镜观测舰外天体"))}),s.text(44,452,"倍率",{size:16,color:s.theme.textDim}),s.progress({x:44,y:466,w:360,h:16},n,{label:"",color:s.theme.accent}),s.button("zoom-in",{x:424,y:452,w:90,h:40},"放大",{size:16})&&(n=Math.min(1,n+.2),i.host.actions.zoomView(1.2)),s.button("zoom-out",{x:524,y:452,w:90,h:40},"缩小",{size:16})&&(n=Math.max(.1,n-.2),i.host.actions.zoomView(1/1.2)),s.panel({x:684,y:130,w:320,h:424},{title:"观测记录 / LOG"}),s.text(708,200,"当前目标是「"+t[e]+"」。",{size:17,maxWidth:280}),s.text(708,244,"放大/缩小会改变视野（FOV），",{size:15,color:s.theme.textDim,maxWidth:280}),s.text(708,266,"把光标对准舷窗外即可观察。",{size:15,color:s.theme.textDim,maxWidth:280}),s.text(708,330,"提示：观景廊的舷窗视野最好。",{size:15,color:s.theme.textDim,maxWidth:280})}}}},Mg={id:"captain-chair",title:"舰长席",subtitle:"指挥席 · CAPTAIN",accent:16765088,create(i){return{draw(t){const e=i.host.actions.isSeated();t.panel({x:20,y:130,w:984,h:424},{title:"舰长日志 / CAPTAIN LOG"}),t.text(48,210,e?"已就座：视野降低，移动暂停。":"尚未就座。",{size:24}),t.button("seat",{x:48,y:260,w:220,h:56},e?"起身":"坐下",{tone:t.theme.accent})&&(i.host.actions.setSeated(!e),i.redraw());const n=i.shell.status;t.keyValue(48,360,900,"舰船状态",n.standby?"低功耗待机":"全系统运行"),t.keyValue(48,392,900,"在位插件",String(n.plugins.running)+" / "+String(n.plugins.total)),t.keyValue(48,424,900,"通讯链路",n.online?"正常":"中断"),t.keyValue(48,456,900,"运行时长",Ui(n.uptime_seconds)),t.text(48,512,"舰长须知：所有面板都在舰上；待机时部分终端会进入低功耗。",{size:15,color:t.theme.textDim})}}}},yg=[fg,mg,gg,_g,xg,vg,Mg];function dc(i){return{id:i.id,title:i.title,subtitle:i.subtitle,accent:i.accent,kind:"minigame",create(t){let e=null,n=0;return{pollers:[new re(()=>t.host.gameApi.get("/api/scores?game="+encodeURIComponent(i.id)+"&limit=5"),2e4,r=>{e=r,n=Math.max(n,Number((r.items||[])[0]?.score??0)),t.redraw()})],idleAnimated:!0,draw(r){r.panel({x:20,y:130,w:600,h:424},{title:"演练说明 / BRIEFING"}),r.text(44,190,i.description,{size:20,maxWidth:552}),i.howTo.forEach((o,l)=>{r.text(44,236+l*30,"· "+o,{size:17,color:r.theme.textDim,maxWidth:552})}),r.button("start",{x:44,y:470,w:240,h:60},"开始演练",{tone:r.theme.accent,disabled:!!t.shell.status.standby})&&t.host.actions.openMinigame(i.id,t.anchor.spec.id),r.text(300,508,"按 E 离开终端 · 演练中按 E / Esc 可随时退出",{size:15,color:r.theme.textDim}),r.panel({x:640,y:130,w:364,h:424},{title:"最佳成绩 / BEST"});const a=e?.items||[];a.length===0&&r.text(664,200,"还没有记录，去创造第一份成绩。",{size:17,color:r.theme.textDim,maxWidth:320}),a.forEach((o,l)=>{const h=196+l*40;r.text(664,h,String(l+1)+". "+String(o.player||"舰长"),{size:18}),r.text(984,h,pe(o.score),{size:18,align:"right",color:r.theme.accent})}),r.text(664,470,i.scoreLabel,{size:15,color:r.theme.textDim}),r.text(664,500,"当前最佳："+pe(n),{size:18})}}}}}const Sg=dc({id:"turret",title:"炮塔模拟器",subtitle:"舱外炮塔 · TURRET",accent:16747114,description:"小行星群正在接近。坐上舷侧炮塔，把它们打成碎片。",howTo:["移动鼠标瞄准，左键开火（每 0.18 秒一发）","小行星撞上舰体会扣完整度，归零即演练失败","每 14 秒来一波，波次越高速度越快","完整度越高，结算奖励分越多"],scoreLabel:"击毁得分（含完整度奖励）"}),wg=dc({id:"repair",title:"损管终端",subtitle:"损管抢修 · DAMAGE CONTROL",accent:16762977,description:"反应堆回路被震断，限时把电力从堆芯接到各个系统。",howTo:["点击导线格子让它旋转 90°","绿色表示已通电，橙色边框是必须接通的系统","接通全部系统即过关，剩余时间折算分数","共三轮，每轮时间更短、网格更乱"],scoreLabel:"抢修得分（含剩余时间奖励）"}),Eg=[Sg,wg],fc=[...ng,...ag,...dg,...yg,...Eg];Object.fromEntries(fc.map(i=>[i.id,i]));function bg(){return fc}class Tg{modules=new Map;register(t){this.modules.set(t.id,t)}get(t){return this.modules.get(t)}list(){return[...this.modules.values()]}}const pc=new Tg;function mc(i){pc.register(i)}const Ag=14,Bs=200,Rg=9,xi={minX:-78,maxX:78,minY:-4,maxY:15,minZ:-24,maxZ:24};class Cg{id="turret";name="舱外炮塔";description="小行星群正在接近，用舷侧炮塔把它们打成碎片。";icon="target";mode="world";ctx=null;group=null;asteroids=[];bolts=[];bursts=[];yaw=0;pitch=0;elapsed=0;waveTimer=0;wave=1;score=0;hull=Bs;destroyed=0;fireCooldown=0;ended=!1;viewpoint(){return{position:new R(46,12.4,26),yaw:Math.PI,pitch:-.05}}start(t){this.ctx=t,this.group=new Ze,this.group.name="minigame-turret",t.scene.add(this.group),this.asteroids=[],this.bolts=[],this.bursts=[],this.elapsed=0,this.waveTimer=0,this.wave=1,this.score=0,this.hull=Bs,this.destroyed=0,this.ended=!1,this.yaw=Math.PI,this.pitch=-.05,this.spawnWave(4),t.setHud({title:"舱外炮塔",score:"得分 0",extra:"舰体完整度 100%",hint:"移动鼠标瞄准 · 左键开火 · Esc/E 退出"})}spawnWave(t){const e=this.ctx;if(!(!e||!this.group))for(let n=0;n<t;n+=1){const s=4+e.rng()*10,r=new cs(s,1),a=r.attributes.position;for(let f=0;f<a.count;f+=1){const g=.75+e.rng()*.5;a.setXYZ(f,a.getX(f)*g,a.getY(f)*g,a.getZ(f)*g)}r.computeVertexNormals();const o=new Ct(r,new Me({color:9209208,roughness:.95,flatShading:!0})),l=(e.rng()-.5)*1.2+Math.PI,h=620+e.rng()*320;o.position.set(Math.cos(l)*h*.35,(e.rng()-.5)*160,Math.sin(l)*h);const d=24+this.wave*3+e.rng()*14,u=new R((e.rng()-.5)*60,(e.rng()-.5)*10,(e.rng()-.5)*30).sub(o.position).normalize().multiplyScalar(d);this.group.add(o),this.asteroids.push({mesh:o,velocity:u,radius:s,hp:Math.max(1,Math.round(s/4)),alive:!0})}}update(t,e){if(this.ended)return;this.elapsed+=t,this.waveTimer+=t,this.fireCooldown=Math.max(0,this.fireCooldown-t),this.waveTimer>Ag&&(this.waveTimer=0,this.wave+=1,e.audio.alarm(),e.toast("第 "+this.wave+" 波小行星接近！","warn"),this.spawnWave(2+this.wave));const n=e.camera;n.position.set(46,12.4,26),n.rotation.set(this.pitch,this.yaw,0,"YXZ");for(const s of this.asteroids){if(!s.alive)continue;s.mesh.position.addScaledVector(s.velocity,t),s.mesh.rotation.x+=t*.4,s.mesh.rotation.y+=t*.3;const r=s.mesh.position;r.x>xi.minX-s.radius&&r.x<xi.maxX+s.radius&&r.y>xi.minY-s.radius&&r.y<xi.maxY+s.radius&&r.z>xi.minZ-s.radius&&r.z<xi.maxZ+s.radius&&(s.alive=!1,this.group?.remove(s.mesh),this.hull=Math.max(0,this.hull-Rg),e.audio.explosion(),e.toast("舰体被击中！完整度 "+Math.round(this.hull/Bs*100)+"%","error"),this.hull<=0&&this.finish(!1))}for(const s of this.bolts){s.mesh.position.x+=s.velocity.x*t,s.mesh.position.y+=s.velocity.y*t,s.mesh.position.z+=s.velocity.z*t,s.life-=t;for(const r of this.asteroids)if(r.alive&&s.mesh.position.distanceTo(r.mesh.position)<r.radius+2.4){r.hp-=1,this.spawnBurst(r.mesh.position,r.radius),r.hp<=0?(r.alive=!1,this.group?.remove(r.mesh),this.destroyed+=1,this.score+=Math.round(r.radius*8),e.audio.explosion()):e.audio.laser(),s.life=0;break}s.life<=0&&this.group?.remove(s.mesh)}this.bolts=this.bolts.filter(s=>s.life>0);for(const s of this.bursts){s.life-=t;const r=s.points.geometry.attributes.position;for(let a=0;a<r.count;a+=1)r.setXYZ(a,r.getX(a)+s.velocities[a*3]*t,r.getY(a)+s.velocities[a*3+1]*t,r.getZ(a)+s.velocities[a*3+2]*t);r.needsUpdate=!0,s.points.material.opacity=Math.max(0,s.life/.8),s.life<=0&&this.group?.remove(s.points)}this.bursts=this.bursts.filter(s=>s.life>0),e.setHud({title:"舱外炮塔 · 第 "+this.wave+" 波",score:"得分 "+this.score+" · 击毁 "+this.destroyed,extra:"舰体完整度 "+Math.round(this.hull/Bs*100)+"%",hint:"左键开火 · Esc/E 退出"}),this.elapsed>180&&this.finish(!0)}spawnBurst(t,e){const n=this.ctx;if(!n||!this.group)return;const s=28,r=new Float32Array(s*3),a=new Float32Array(s*3);for(let h=0;h<s;h+=1){r[h*3]=t.x,r[h*3+1]=t.y,r[h*3+2]=t.z;const d=14+n.rng()*22;a[h*3]=(n.rng()-.5)*d,a[h*3+1]=(n.rng()-.5)*d,a[h*3+2]=(n.rng()-.5)*d}const o=new Le;o.setAttribute("position",new Xe(r,3));const l=new Km(o,new oc({color:16763024,size:Math.max(1.4,e*.12),transparent:!0,opacity:1,depthWrite:!1}));this.group.add(l),this.bursts.push({points:l,life:.8,velocities:a})}onPointerMove(t,e){this.yaw-=t*.0022,this.pitch=Math.max(-1.2,Math.min(1.2,this.pitch-e*.0022))}onPointerDown(){const t=this.ctx;if(!t||!this.group||this.fireCooldown>0)return;this.fireCooldown=.18;const e=new R;t.camera.getWorldDirection(e);const n=new Ct(new Jn(.35,.35,6,8),new fe({color:9433343}));n.position.copy(t.camera.position).addScaledVector(e,6),n.quaternion.setFromUnitVectors(new R(0,1,0),e),this.group.add(n),this.bolts.push({mesh:n,velocity:{x:e.x*420,y:e.y*420,z:e.z*420},life:2.4}),t.audio.laser()}finish(t){const e=this.ctx;if(!e||this.ended)return;this.ended=!0;const n=t?Math.round(this.hull*20):0,s=this.score+n;e.submitScore("turret",s,Math.round(this.elapsed*1e3),"击毁 "+this.destroyed+" 颗").then(r=>{e.finish({title:t?"炮塔演练完成":"舰体受损，演练终止",lines:["击毁小行星："+this.destroyed+" 颗",t?"完整度奖励：+"+n:"完整度："+Math.round(this.hull)+"%",r.ok?"本次得分 "+s+"，历史最佳 "+(r.best??s)+"，排名第 "+(r.rank??1):"成绩未能保存："+(r.error||"未知原因")],score:s,canRetry:!0})})}dispose(t){this.group&&(t.scene.remove(this.group),this.group.traverse(e=>{const n=e;n.geometry&&n.geometry.dispose()})),this.group=null,this.asteroids=[],this.bolts=[],this.bursts=[],this.ctx=null}}mc(new Cg);const Wt=6,en=4,Wr=75,oe=[1,2,4,8];class Pg{id="repair";name="损管抢修";description="反应堆回路被震断，限时把电力接到各个系统。";icon="wrench";mode="screen";ctx=null;cells=[];targets=[];timeLeft=Wr;round=1;score=0;elapsed=0;solved=!1;failed=!1;hint="点击导线旋转，把电力从左侧堆芯引到右侧系统接口。";lastTick=0;start(t){this.ctx=t,this.round=1,this.score=0,this.elapsed=0,this.buildRound(),t.setHud(null)}buildRound(){const t=this.ctx;if(!t)return;this.timeLeft=Math.max(35,Wr-(this.round-1)*10),this.solved=!1,this.failed=!1;const e=t.rng.bind(t),n=[];let s=Math.floor(e()*en);for(let c=0;c<Wt;c+=1)if(n.push([c,s]),c<Wt-1&&e()>.45){const u=s===0?1:s===en-1?-1:e()>.5?1:-1;n.push([c,s+u]),s+=u}this.cells=[];for(let c=0;c<Wt*en;c+=1)this.cells.push({mask:0,fixed:!1,powered:!1});const r=(c,u)=>{const f=this.cells[c[1]*Wt+c[0]],g=this.cells[u[1]*Wt+u[0]];c[1]>u[1]&&(f.mask|=oe[0]),c[0]<u[0]&&(f.mask|=oe[1]),c[1]<u[1]&&(f.mask|=oe[2]),c[0]>u[0]&&(f.mask|=oe[3]),u[1]<c[1]&&(g.mask|=oe[0]),u[0]>c[0]&&(g.mask|=oe[1]),u[1]>c[1]&&(g.mask|=oe[2]),u[0]<c[0]&&(g.mask|=oe[3])},a=this.cells[n[0][1]*Wt+0];a.mask|=oe[3],a.fixed=!0;for(let c=0;c<n.length-1;c+=1)r(n[c],n[c+1]);const o=n[n.length-1];this.cells[o[1]*Wt+(Wt-1)].mask|=oe[1],this.targets=[o[1]*Wt+(Wt-1)];const l=(o[1]+2)%en,h=Wt-1,d=l*Wt+h;this.targets.includes(d)||(this.cells[d].mask|=oe[1],this.targets.push(d));for(const c of this.cells){if(c.mask===0)continue;const u=Math.floor(e()*4);c.mask=Xr(c.mask,u)}this.cells[n[0][1]*Wt].mask=Xr(this.cells[n[0][1]*Wt].mask,0),this.cells[n[0][1]*Wt].mask|=oe[3]}computePower(){for(const e of this.cells)e.powered=!1;const t=[];for(let e=0;e<en;e+=1){const n=e*Wt;this.cells[n].mask&oe[3]&&(this.cells[n].powered=!0,t.push(n))}for(;t.length>0;){const e=t.shift(),n=e%Wt,s=Math.floor(e/Wt),r=this.cells[e].mask,a=[[0,-1,oe[0],oe[2]],[1,0,oe[1],oe[3]],[0,1,oe[2],oe[0]],[-1,0,oe[3],oe[1]]];for(const[o,l,h,d]of a){if(!(r&h))continue;const c=n+o,u=s+l;if(c<0||c>=Wt||u<0||u>=en)continue;const f=u*Wt+c;this.cells[f].mask&d&&(this.cells[f].powered||(this.cells[f].powered=!0,t.push(f)))}}return this.targets.every(e=>this.cells[e].powered)}update(t,e){this.solved||this.failed||(this.elapsed+=t,this.timeLeft-=t,this.timeLeft<=0&&(this.failed=!0,e.audio.alarm(),e.submitScore("repair",this.score,Math.round(this.elapsed*1e3),"第 "+this.round+" 轮超时").then(n=>{e.finish({title:"抢修超时",lines:["完成轮数："+(this.round-1),"本次得分："+this.score,n.ok?"历史最佳 "+(n.best??this.score):"成绩未保存："+(n.error||"")],score:this.score,canRetry:!0})})),this.timeLeft<10&&performance.now()-this.lastTick>1e3&&(this.lastTick=performance.now(),e.audio.alarm()))}draw(t,e){t.panel({x:20,y:130,w:40+Wt*118+20,h:en*118+60},{title:"电力回路 / CIRCUIT"});for(let o=0;o<en;o+=1)for(let l=0;l<Wt;l+=1){const h=o*Wt+l,d=this.cells[h],c=40+l*118,u=150+o*118,f={x:c+6,y:u+6,w:106,h:106},g=this.targets.includes(h),v=t.isHovered("cell-"+h);t.ctx.fillStyle=d.powered?"rgba(80, 220, 160, 0.22)":v?"rgba(90, 150, 200, 0.22)":"rgba(14, 28, 40, 0.6)",t.ctx.fillRect(f.x,f.y,f.w,f.h),t.ctx.strokeStyle=g?t.theme.warn:"rgba(90, 150, 190, 0.45)",t.ctx.lineWidth=g?3:1.5,t.ctx.strokeRect(f.x+.5,f.y+.5,f.w-1,f.h-1);const m=f.x+f.w/2,p=f.y+f.h/2,y=f.w*.32,_=d.powered?t.theme.ok:"rgba(150, 190, 220, 0.55)";if(t.ctx.strokeStyle=d.powered?t.theme.ok:_,t.ctx.lineWidth=9,t.ctx.lineCap="round",[[m,p,m,p-y],[m,p,m+y,p],[m,p,m,p+y],[m,p,m-y,p]].forEach((P,T)=>{d.mask&oe[T]&&(t.ctx.beginPath(),t.ctx.moveTo(P[0],P[1]),t.ctx.lineTo(P[2],P[3]),t.ctx.stroke())}),t.ctx.beginPath(),t.ctx.arc(m,p,6,0,Math.PI*2),t.ctx.fillStyle=d.powered?t.theme.ok:_,t.ctx.fill(),d.powered){const P=.5+.5*Math.sin(performance.now()/200+h);t.ctx.globalAlpha=.25*P,t.ctx.fillStyle=t.theme.ok,t.ctx.fillRect(f.x,f.y,f.w,f.h),t.ctx.globalAlpha=1}}t.panel({x:40+Wt*118+40,y:130,w:230,h:en*118+60},{title:"抢修进度 / STATUS"}),t.text(40+Wt*118+64,190,"剩余时间",{size:16,color:t.theme.textDim}),t.text(40+Wt*118+64,232,Math.max(0,this.timeLeft).toFixed(1)+" s",{size:30,weight:"bold",color:this.timeLeft<15?t.theme.error:t.theme.text}),t.progress({x:40+Wt*118+64,y:250,w:182,h:14},this.timeLeft/Wr,{color:this.timeLeft<15?t.theme.error:t.theme.accent,showValue:!1});const a=this.targets.filter(o=>this.cells[o].powered).length;t.text(40+Wt*118+64,310,"已接通系统",{size:16,color:t.theme.textDim}),t.text(40+Wt*118+64,350,a+" / "+this.targets.length,{size:30,weight:"bold"}),t.text(40+Wt*118+64,400,"当前轮次",{size:16,color:t.theme.textDim}),t.text(40+Wt*118+64,436,String(this.round),{size:28,weight:"bold",color:t.theme.accent}),t.text(40+Wt*118+64,500,"得分 "+this.score,{size:20,color:t.theme.accent}),t.text(40,150+en*118+30,this.hint,{size:15,color:t.theme.textDim})}onScreenClick(t){const r=Math.floor((t.cursor.x-40)/118),a=Math.floor((t.cursor.y-150)/118);if(r<0||r>=Wt||a<0||a>=en)return;const o=a*Wt+r,l=this.cells[o];if(!(!l||l.mask===0)&&(l.mask=Xr(l.mask,1),this.ctx?.audio.chime("repair"),this.computePower())){this.solved=!0;const h=Math.round(this.timeLeft*40+500);this.score+=h,this.ctx?.toast("回路接通！本轮 +"+h+" 分","ok"),window.setTimeout(()=>{const d=this.ctx;d&&(this.round+=1,this.round>3?d.submitScore("repair",this.score,Math.round(this.elapsed*1e3),"完成 3 轮抢修").then(c=>{d.finish({title:"抢修完成",lines:["完成轮数：3","剩余时间奖励已计入",c.ok?"本次得分 "+this.score+"，历史最佳 "+(c.best??this.score)+"，排名第 "+(c.rank??1):"成绩未保存："+(c.error||"")],score:this.score,canRetry:!0})}):this.buildRound())},900)}}}function Xr(i,t){let e=i;for(let n=0;n<(t%4+4)%4;n+=1)e=(e<<1|e>>3)&15;return e}const Lg=new Pg;mc(Lg);class Dg{constructor(t,e,n,s){this.container=t,this.hudRoot=e,this.bootstrap=n,this.qualityLevel=Mc(n.quality);const r=hr[this.qualityLevel];Object.assign(this.quality,r),this.jumpIntervalMinutes=n.jump_interval_minutes,this.renderer=new Vm({canvas:s,antialias:r.antialias,powerPreference:"high-performance"}),this.renderer.setPixelRatio(Math.min(window.devicePixelRatio,r.pixelRatio)),this.renderer.setSize(t.clientWidth,Math.max(1,t.clientHeight),!1),this.renderer.outputColorSpace=je,this.renderer.toneMapping=Dl,this.renderer.toneMappingExposure=1.3,this.renderer.setClearColor(198155,1),this.camera=new Ve(72,t.clientWidth/Math.max(1,t.clientHeight),.1,r.viewDistance),this.hud=new h0(e),this.input=new u0(s),this.audio=new n0(n.enable_audio),this.shell.playerName=this.playerName,this.ship=Y0(this.scene,this.collision,a=>this.hud.toast(a,"info",1200)),this.materials=this.ship.materials,j0(this.scene,this.collision,this.materials,this.ship.rooms),this.player=new v0(this.ship.ladders),this.player.spawn(this.ship.spawn,this.ship.spawnYaw),this.space=new ml(this.scene,this.camera,{quality:r}),this.systemIndex=Math.floor(Math.random()*1e3),this.warpCountdown=this.nextWarpDelay(),this.buildTerminals(),this.input.onLockLost=()=>{this.mode==="world"&&this.booted&&this.showPauseOverlay()},window.addEventListener("resize",this.handleResize),document.addEventListener("visibilitychange",this.handleVisibility),window.addEventListener("keydown",this.handleKeyDown,!0),window.__neobotStarship=this}scene=new Wm;camera;collision=new o0;shell=new D0;hud;input;textCapture=new I0;materials;quality={...hr.medium};actions=this;jumpIntervalMinutes;qualityLevel;renderer;ship;space;player;terminals=[];audio;raycaster=new e0;clockLast=0;rafId=0;running=!1;visible=!0;mode="boot";focused=null;candidate=null;focusBlend=0;focusFrom=new R;focusLook=new R;currentLook=new R;boosts=new Map;unlocked=new Set;statusPoller=null;warpCountdown=0;seated=!1;systemIndex=0;fpsAccumulator=0;fpsFrames=0;fps=0;activeMinigame=null;minigameStation=null;minigameScreenMode=!1;minigameStartedAt=0;playerName=Sc();pausedOverlay=null;minigameContext=null;savedView=null;booted=!1;start(){this.running||(this.running=!0,this.booted=!0,this.mode="world",this.clockLast=performance.now(),this.audio.resume(),this.input.requestLock(),this.statusPoller=new re(()=>Mi.get("/api/status"),5e3,t=>this.applyStatus(t),()=>{}),this.statusPoller.start(!0),this.rafId=requestAnimationFrame(this.frame),this.hud.toast("欢迎登舰，"+this.playerName+"。WASD 移动，走近终端按 E 使用，Esc 打开菜单。","info",7e3))}dispose(){this.running=!1,cancelAnimationFrame(this.rafId),this.statusPoller?.stop(),this.space.dispose(),this.ship.dispose();for(const t of this.terminals)t.dispose();this.input.dispose(),this.textCapture.close(),this.audio.dispose(),window.removeEventListener("resize",this.handleResize),document.removeEventListener("visibilitychange",this.handleVisibility),window.removeEventListener("keydown",this.handleKeyDown,!0),this.renderer.dispose()}handleResize=()=>{const t=Math.max(1,this.container.clientWidth),e=Math.max(1,this.container.clientHeight);this.renderer.setSize(t,e,!1),this.camera.aspect=t/e,this.camera.updateProjectionMatrix()};handleVisibility=()=>{this.visible=!document.hidden,this.visible&&(this.clockLast=performance.now())};handleKeyDown=t=>{if(this.mode==="minigame"&&this.activeMinigame&&!this.minigameScreenMode){if(t.key==="Escape"||t.key==="e"||t.key==="E"){this.exitMinigame("已被玩家终止"),t.preventDefault();return}this.activeMinigame.onKey?.(t.key,this.ensureMinigameContext());return}if(t.key==="Escape"){(this.mode==="terminal"||this.minigameScreenMode)&&(this.minigameScreenMode?this.exitMinigame("已被玩家终止"):this.blurTerminal(),t.preventDefault());return}if(t.key==="e"||t.key==="E"){this.minigameScreenMode?this.exitMinigame("已被玩家终止"):this.mode==="terminal"?this.blurTerminal():this.mode==="world"&&this.interact();return}if(t.key==="f"||t.key==="F"){this.mode==="world"&&this.toggleSeat();return}(t.key==="m"||t.key==="M")&&this.mode==="world"&&!this.pausedOverlay&&this.showPauseOverlay()};buildTerminals(){const t=new Map;for(const e of bg())t.set(e.id,e);for(const e of this.ship.anchors.values()){const n=e.spec.target,s=t.get(n);if(!s||e.spec.kind==="minigame"&&s.id!==n)continue;const r=new H0(s,this,e);this.terminals.push(r)}this.applyStatusAvailability()}applyStatusAvailability(){for(const t of this.terminals)t.setAvailability(this.shell.availability(t.definition.id))}toast(t,e="info"){this.hud.toast(t,e)}confirm(t){return this.hud.confirm(t)}openMinigame(t,e){const n=e?this.terminals.find(s=>s.anchor.spec.id===e)??null:null;this.startMinigame(t,n)}get consoleApi(){return E0}get gameApi(){return Mi}requestRedraw(){for(const t of this.terminals)t.markDirty()}triggerWarp(t){if(this.space.warping)return!1;const e=this.space.triggerWarp(()=>{this.systemIndex+=1,this.hud.toast("已抵达新星系："+this.systemName(),"ok",5e3),this.unlockAchievement("first-jump",t?"手动跃迁":"自动跃迁")});return e&&(this.audio.warp(),this.hud.setBanner("跃迁引擎点火 · 全舰注意","info"),window.setTimeout(()=>{!this.space.warping&&!this.shell.status.standby&&this.hud.setBanner(null)},4200)),e}warping(){return this.space.warping}warpPhase(){return this.space.warpPhase}systemName(){const t=["天鹅座 λ-4","猎户悬臂 K-17","南门二 β","天苑四 ε","蛇夫座 9","武仙座 τ","船底座 HD-7","仙女座 M31-附","半人马 ζ","天琴座 Vega-2"];return t[this.systemIndex%t.length]}playChime(t){this.audio.chime(t)}playMusic(t){this.audio.playMusic(t)}stopMusic(){this.audio.stopMusic()}setMusicActive(t){t||this.audio.stopMusic()}boost(t,e){this.boosts.set(t,{remaining:e})}boostRemaining(t){return this.boosts.get(t)?.remaining??0}unlockAchievement(t,e=""){this.unlocked.has(t)||(this.unlocked.add(t),Mi.post("/api/achievements",{key:t,detail:e}))}setSeated(t){this.seated=t,this.player.velocity.set(0,0,0)}isSeated(){return this.seated}lookAtTarget(t){const e={主行星:new R(1400,-260,-900),伴星卫星:new R(900,180,1200),小行星带:new R(-600,120,900),航道上的货船:new R(400,60,-500)},s=(e[t]||e.主行星).clone().sub(this.camera.position).normalize();this.player.yaw=Math.atan2(-s.x,-s.z),this.player.pitch=Math.asin(Rh.clamp(s.y,-1,1)),this.hud.toast("望远镜已对准："+t,"info")}zoomView(t){this.camera.fov=Math.max(18,Math.min(96,this.camera.fov/t)),this.camera.updateProjectionMatrix()}nextWarpDelay(){return this.jumpIntervalMinutes<=0?Number.POSITIVE_INFINITY:this.jumpIntervalMinutes*60*(.6+Math.random()*.7)}frame=t=>{if(this.rafId=requestAnimationFrame(this.frame),!this.visible){this.clockLast=t;return}const e=Math.min(.05,Math.max(0,(t-this.clockLast)/1e3));this.clockLast=t,this.fpsAccumulator+=e,this.fpsFrames+=1,this.fpsAccumulator>.5&&(this.fps=Math.round(this.fpsFrames/this.fpsAccumulator),this.fpsAccumulator=0,this.fpsFrames=0),this.updateBoosts(e),this.space.update(e),this.mode==="minigame"&&this.activeMinigame&&!this.minigameScreenMode?this.updateWorldMinigame(e):this.focused&&(this.mode==="terminal"||this.mode==="minigame")?this.updateFocusedTerminal(e):this.updateWorld(e);for(const n of this.terminals)n!==this.focused&&n.update(e);this.focused?.update(e),this.updateHud(),this.renderer.render(this.scene,this.camera),this.input.endFrame()};updateBoosts(t){for(const[e,n]of this.boosts)n.remaining-=t,n.remaining<=0&&this.boosts.delete(e)}updateWorld(t){const e=this.input.locked,n=this.boostRemaining("sprint")>0?1.25:1;this.player.update(t,this.collision,this.input,{enabled:e&&!this.seated,speedScale:n,jumpScale:this.boostRemaining("jump")>0?1.15:1,onStep:s=>this.audio.footstep(s)}),this.camera.position.copy(this.player.eyePosition()),this.seated&&(this.camera.position.y-=.5),this.camera.rotation.set(this.player.pitch,this.player.yaw,0,"YXZ"),this.candidate=this.findCandidate(),this.updatePrompt(),!this.space.warping&&Number.isFinite(this.warpCountdown)&&(this.warpCountdown-=t,this.warpCountdown<=0&&(this.warpCountdown=this.nextWarpDelay(),this.triggerWarp(!1)&&this.hud.toast("舰载 AI 规划了一次自动跃迁。","info",4e3)))}updateFocusedTerminal(t){const e=this.focused;if(!e){this.mode="world";return}this.focusBlend=Math.min(1,this.focusBlend+t*4.5);const n=e.focusView(),s=Ig(this.focusBlend);this.camera.position.lerpVectors(this.focusFrom,n.position,s),this.currentLook.copy(this.focusLook).lerp(n.target,s),this.camera.lookAt(this.currentLook),this.raycaster.setFromCamera(new Ht(this.input.pointer.x,this.input.pointer.y),this.camera);const r=this.raycaster.intersectObject(e.screen.mesh,!1),a=r.length>0?r[0]:null;e.handlePointer(a,!1,this.input.pointer.wheel),this.input.pointer.clicked&&(this.activeMinigame&&this.minigameScreenMode?a&&this.activeMinigame.onScreenClick?.(e.ui,this.ensureMinigameContext()):(e.ui.clicked=!0,e.markDirty())),this.activeMinigame&&this.minigameScreenMode&&(this.activeMinigame.update?.(t,this.ensureMinigameContext()),e.markDirty())}updateWorldMinigame(t){const e=this.activeMinigame;if(!e){this.mode="world";return}const n=this.ensureMinigameContext();e.update?.(t,n),(this.input.pointer.deltaX!==0||this.input.pointer.deltaY!==0)&&e.onPointerMove?.(this.input.pointer.deltaX,this.input.pointer.deltaY,n),this.input.pointer.clicked&&e.onPointerDown?.(n)}updateHud(){if(this.mode==="terminal"){this.hud.setCrosshairVisible(!1);const r=this.minigameScreenMode?"演练中：点击操作 · E / Esc 退出":this.focused?.definition.id==="logs"?"日志终端 · 点击条目查看 · E / Esc 离开":"终端已聚焦 · 鼠标操作 · E / Esc 离开";this.hud.setStatus([r+" · "+this.fps+" FPS"]);return}if(this.mode==="minigame"){this.hud.setCrosshairVisible(!this.minigameScreenMode,"pointer");return}const t=q0(this.ship.rooms,this.player.position),e=[];e.push((t?t.label:"舰内")+" · "+this.fps+" FPS");const n=this.space.warping?"跃迁中":"巡航";e.push((this.shell.status.standby?"低功耗待机":n+" · "+this.systemName())+" · 插件 "+this.shell.status.plugins.running+"/"+this.shell.status.plugins.total+(this.shell.status.online?" · 通讯正常":" · 通讯中断"));const s=[];this.boostRemaining("sprint")>0&&s.push("疾跑增益 "+this.boostRemaining("sprint").toFixed(0)+"s"),this.boostRemaining("jump")>0&&s.push("跳跃增益 "+this.boostRemaining("jump").toFixed(0)+"s"),s.length>0&&e.push(s.join(" · ")),this.input.locked?e.push("WASD 移动 · Shift 潜行 · Ctrl 疾跑 · 空格跳跃 · E 交互 · F 就座 · M 菜单"):e.push("点击画面继续操作 · M 打开菜单"),this.hud.setStatus(e),this.hud.setCrosshairVisible(this.input.locked&&!this.seated,this.candidate?"pointer":"dot")}findCandidate(){const t=this.camera.position,e=new R;this.camera.getWorldDirection(e);let n=null,s=0;for(const r of this.terminals){const o=r.screen.worldCenter(new R).clone().sub(t),l=o.length();if(l>4.2)continue;const h=o.normalize().dot(e);if(h<.45)continue;const d=h*2-l*.12;d>s&&(s=d,n=r)}return n}updatePrompt(){const t=this.candidate;if(!t){this.hud.showPrompt(null);return}const e=t.anchor.spec;if(!t.interactable){this.hud.showPrompt(e.label+" · 终端已下线（"+t.availabilityReason+"）");return}this.hud.showPrompt(e.label+" · "+e.hint)}interact(){const t=this.candidate;if(t){if(!t.interactable){this.hud.toast(t.availabilityReason||"该终端当前不可用","warn"),this.audio.alarm();return}if(t.definition.kind==="minigame"){this.startMinigame(t.definition.id,t);return}this.focusTerminal(t)}}focusTerminal(t){this.focused=t,this.mode="terminal",this.input.mode="terminal",this.input.releaseLock(),this.focusFrom.copy(this.camera.position),this.focusLook.copy(this.camera.position).add(new R(0,0,-1).applyQuaternion(this.camera.quaternion).multiplyScalar(8)),this.focusBlend=0,t.focus(),this.hud.showPrompt(null),this.audio.chime("terminal")}blurTerminal(){this.focused&&this.focused.blur(),this.focused=null,this.mode="world",this.input.mode="world",this.textCapture.close(),this.focusBlend=0,this.input.requestLock()}toggleSeat(){this.seated=!this.seated,this.hud.toast(this.seated?"已就座（按 F 起身）":"已起身","info")}startMinigame(t,e){const n=pc.get(t);if(!n){this.hud.toast("该小游戏没有客户端模块（可能需要更新游戏前端）","warn");return}this.activeMinigame&&this.stopMinigameModule(),e||(e=this.terminals.find(r=>r.definition.id===t)??null),this.minigameStation=e,this.activeMinigame=n,this.minigameScreenMode=n.mode==="screen",this.minigameStartedAt=performance.now(),this.savedView={position:this.player.position.clone(),yaw:this.player.yaw,pitch:this.player.pitch};const s=this.ensureMinigameContext();if(n.start?.(s),n.mode==="world"){const r=n.viewpoint?.(s);r&&(this.player.yaw=r.yaw,this.player.pitch=r.pitch,this.camera.position.copy(r.position),this.camera.rotation.set(r.pitch,r.yaw,0,"YXZ")),this.mode="minigame",this.input.mode="minigame",this.input.requestLock(),this.hud.showPrompt(null),this.audio.alarm()}else{if(this.mode="minigame",this.input.mode="terminal",e)this.focused=e,this.focusFrom.copy(this.camera.position),this.focusLook.copy(this.camera.position),this.focusBlend=0,e.setOverride((r,a)=>n.draw?.(r,this.ensureMinigameContext())??void 0),e.focus();else{this.hud.toast("未找到演练终端（"+t+"），已取消","warn"),this.activeMinigame=null,this.mode="world";return}this.input.releaseLock()}this.hud.toast("进入演练："+n.name+" · "+n.description,"ok",5e3)}ensureMinigameContext(){return this.minigameContext?this.minigameContext:(this.minigameContext={scene:this.scene,camera:this.camera,input:this.input,hud:this.hud,audio:this.audio,shell:this.shell,quality:this.quality,actions:this,playerPosition:this.player.position,submitScore:async(t,e,n,s)=>{const r=await Mi.post("/api/scores",{game:t,score:e,duration_ms:n,detail:s,player:this.playerName});return r.ok?{ok:!0,best:r.data?.best,rank:r.data?.rank}:{ok:!1,error:r.error||"保存失败"}},leaderboard:(t,e)=>Mi.get("/api/scores?game="+encodeURIComponent(t)+"&limit="+e),toast:(t,e)=>this.hud.toast(t,e||"info"),exit:t=>this.exitMinigame(t||"演练结束"),finish:t=>this.finishMinigame(t),setHud:t=>this.hud.setMinigame(t),rng:()=>Math.random()},this.minigameContext)}finishMinigame(t){this.hud.setMinigame(null);const e=this.activeMinigame?.id??"";this.hud.confirm({title:t.title,body:t.lines.join(`
`)+`

本次得分：`+t.score,confirmLabel:t.canRetry?"再来一局":"结束",cancelLabel:"返回舰内"}).then(n=>{const s=this.minigameStation;n&&e?(this.stopMinigameModule(),this.startMinigame(e,s)):this.exitMinigame("演练结束")})}stopMinigameModule(){this.activeMinigame&&(this.activeMinigame.dispose?.(this.ensureMinigameContext()),this.activeMinigame=null),this.minigameStation?.setOverride(null)}exitMinigame(t){if(!this.activeMinigame&&this.mode!=="minigame")return;const e=this.activeMinigame?.id;this.stopMinigameModule(),this.hud.setMinigame(null),this.minigameStation&&this.minigameStation.blur(),this.minigameStation=null,this.minigameScreenMode=!1,this.focused=null,this.mode="world",this.input.mode="world",this.savedView?(this.player.spawn(this.savedView.position,this.savedView.yaw),this.player.pitch=this.savedView.pitch,this.savedView=null):this.player.spawn(this.ship.spawn,this.ship.spawnYaw),this.camera.fov=72,this.camera.updateProjectionMatrix(),this.input.requestLock(),this.hud.toast("已返回舰内（"+t+"）","info"),e&&this.unlockAchievement("minigame-"+e,"完成一次演练")}applyStatus(t){this.shell.update(t),this.applyStatusAvailability(),this.requestRedraw(),t.standby?this.hud.setBanner("舰船处于低功耗待机："+(t.reason||"未说明原因")+" · 可在主控台恢复运行","warn"):this.hud.setBanner(null)}showPauseOverlay(){if(this.pausedOverlay)return;const t=document.createElement("div");t.className="game-menu-overlay",t.innerHTML='<div class="game-menu"><h2>NeoBot 星舰</h2><p class="menu-sub">舰长：'+er(this.playerName)+" · "+er(this.systemName())+'</p><div class="menu-rows">'+Yr("画质",["low","medium","high"],this.qualityLevel,"quality")+Yr("鼠标灵敏度",["0.5","1","1.5","2"],String(this.input.sensitivity),"sens")+Yr("垂直视角",["normal","inverted"],this.input.invertY?"inverted":"normal","invert")+'</div><div class="menu-actions"><button data-action="resume" class="primary">继续游戏</button><button data-action="name">修改舰长名</button><button data-action="console">返回控制台</button></div><p class="menu-hint">提示：走近终端按 E 使用；待机状态下部分终端会离线。</p></div>',t.addEventListener("click",e=>{const n=e.target,s=n.dataset.action,r=n.dataset.value;s==="resume"?(this.closePauseOverlay(),this.input.requestLock()):s==="console"?window.location.href=new URL("../",window.location.href).toString():s==="name"?this.hud.ask({title:"舰长名",value:this.playerName}).then(a=>{a&&(this.playerName=a.slice(0,32),wc(this.playerName),this.shell.playerName=this.playerName),this.closePauseOverlay(),this.showPauseOverlay()}):s==="quality"&&r?(this.applyQuality(r),this.closePauseOverlay(),this.showPauseOverlay()):s==="sens"&&r?(this.input.sensitivity=Number(r),this.closePauseOverlay(),this.showPauseOverlay()):s==="invert"&&r&&(this.input.invertY=r==="inverted",this.closePauseOverlay(),this.showPauseOverlay())}),this.hudRoot.appendChild(t),this.pausedOverlay=t,this.input.releaseLock()}closePauseOverlay(){this.pausedOverlay?.remove(),this.pausedOverlay=null}applyQuality(t){this.qualityLevel=t,yc(t);const e=hr[t];Object.assign(this.quality,e),this.renderer.setPixelRatio(Math.min(window.devicePixelRatio,e.pixelRatio)),this.camera.far=e.viewDistance,this.camera.updateProjectionMatrix(),this.space.dispose(),this.space=new ml(this.scene,this.camera,{quality:e}),this.hud.toast("画质已切换为「"+e.label+"」","ok")}}function Ig(i){return 1-Math.pow(1-i,3)}function er(i){return String(i).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")}function Yr(i,t,e,n){return'<div class="menu-row"><span>'+er(i)+"</span><div>"+t.map(s=>'<button data-action="'+n+'" data-value="'+s+'" class="'+(s===e?"active":"")+'">'+er(s)+"</button>").join("")+"</div></div>"}async function Ug(){const i=document.getElementById("app"),t=document.getElementById("starship-canvas"),e=document.getElementById("starship-hud"),n=document.getElementById("starship-boot"),s=document.getElementById("starship-boot-text");if(!i||!t||!e||!n||!s)return;const r=u=>{s.textContent=u};r("正在校验面板会话…");let a=!0;try{const u=localStorage.getItem("neobot-dashboard-token")||"";a=(await fetch(ks()+"/api/auth/me",{cache:"no-store",headers:u?{"X-Token":u}:void 0})).ok}catch{a=!0}if(!a){n.classList.add("error"),s.innerHTML='需要先登录网页面板才能登舰。<br /><a href="'+Ec()+'#/login">前往登录</a>';return}r("正在读取舰载配置…");const o=await Mi.get("/api/bootstrap");if(!o.ok||!o.data){n.classList.add("error"),s.textContent="无法读取游戏配置："+(o.error||"未知错误");return}const l=o.data;r("正在装配星舰…");let h=null;const d=()=>{if(!h){n.classList.add("hidden");try{h=new Dg(i,e,l,t),h.start();const u=()=>h?.dispose()}catch(u){n.classList.remove("hidden"),n.classList.add("error"),s.textContent="星舰装配失败："+u.message}}};n.innerHTML='<div class="boot-panel"><h1>'+Tl(l.title)+'</h1><p class="boot-sub">NEOBOT STARSHIP · '+Tl(l.version||"")+'</p><ul class="boot-list"><li>WASD 移动 · 鼠标看方向 · 空格跳跃 · Shift 潜行 · Ctrl 疾跑</li><li>走近全息终端按 <kbd>E</kbd> 使用（主控台、插件、配置、系统、用量、分析、通讯、日志）</li><li>机库与观景廊可以进入小游戏：舱外炮塔、损管抢修</li><li>舰桥的星图导航台可以手动跃迁；航行中也会自动跃迁</li></ul><button class="boot-enter">登舰</button><p class="boot-hint">进入后浏览器会请求鼠标指针锁定；按 Esc 可释放并打开菜单。</p></div>',n.querySelector(".boot-enter")?.addEventListener("click",d),document.addEventListener("keydown",u=>{u.key==="Enter"&&!n.classList.contains("hidden")&&d()},{once:!1})}function Tl(i){return String(i).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")}Ug();
