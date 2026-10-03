/** Actual HbA1c from PhysioNet v1.1.3 demographics; all other values are synthetic demo fixtures. */
export const cohort = [5.5,5.6,5.9,6.4,5.7,5.8,5.3,5.6,6.1,6,6,5.6,5.7,5.5,5.5,5.5].map((a1c,i)=>({id:String(i+1).padStart(3,'0'),a1c,group:a1c>=5.7?'Prediabetes':'Elevated-normal'}));
export function point(id,minute){
 const n=Number(id); const wave=Math.sin(minute/9+n)*7; const risk=Math.max(8,Math.min(94,35+n%5*6+minute*.36+wave));
 return {minute,risk:Math.round(risk),hr:Math.round(69+n%9+minute*.12+Math.sin(minute/8)*3),hrv:Math.round(54-n%8-minute*.14),eda:+(1.1+n%4*.15+minute*.004).toFixed(2),temp:+(32.4+Math.sin(minute/18)*.3).toFixed(1),quality:minute>=42&&minute<=48?34:94+n%4,movement:minute>=42&&minute<=48?'High':'Low'};
}
export function history(id,end){return Array.from({length:end+1},(_,i)=>point(id,i));}
