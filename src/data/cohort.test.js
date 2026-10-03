import {test} from 'node:test';
import assert from 'node:assert/strict';
import {cohort,point,history} from './cohort.js';
test('observed cohort labels are balanced and contain all participants',()=>{assert.equal(new Set(cohort.map(p=>p.id)).size,16);assert.equal(cohort.filter(p=>p.group==='Prediabetes').length,8);assert.equal(cohort.find(p=>p.id==='004').a1c,6.4)});
test('replay remains bounded and marks motion-corrupted windows',()=>{for(const p of cohort)for(let t=0;t<=90;t++){const v=point(p.id,t);assert.ok(v.risk>=0&&v.risk<=100);assert.ok(v.quality>=0&&v.quality<=100)}assert.ok(point('004',45).quality<50);assert.ok(point('004',50).quality>50);assert.equal(history('004',32).length,33)});
