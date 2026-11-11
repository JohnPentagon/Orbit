export function BrandMark({className='',decorative=false}:{className?:string;decorative?:boolean}){
 return <img className={'orbit-brand-mark '+className} src="/brand/orbit-mark.svg" alt={decorative?'':'ORBIT constellation'} aria-hidden={decorative||undefined} width={128} height={128}/>;
}
export function BrandLogo({className=''}:{className?:string}){
 return <span className={'orbit-brand-logo '+className} aria-label="ORBIT by Pentagon Solutions"><BrandMark decorative/><span className="orbit-brand-type"><strong>ORBIT</strong><small>by Pentagon Solutions</small></span></span>;
}
