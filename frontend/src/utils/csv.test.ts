import test from 'node:test';
import assert from 'node:assert/strict';
import {csvCell, ordersCsv} from './csv';
test('CSV escapes quotes, commas and embedded newlines', () => {
  assert.equal(csvCell('A,"B"\nC'), '"A,""B""\nC"');
  assert.equal(csvCell(null), '""');
});
test('Untrusted formula cells are rendered as text in spreadsheet applications', () => {
  for (const input of ['=1+1', '+CMD', '-CMD', '@SUM(A1)', '\t=SUM(A1)', '\r\n+CMD']) assert.ok(csvCell(input).startsWith('"\''));
  assert.equal(csvCell(-10), '"-10"');
  assert.equal(csvCell('Berry Store'), '"Berry Store"');
});
test('Orders export uses safe CSV encoding for every user-controlled column', () => {
  const result = ordersCsv([{id: 'ORD-1',user_id: 1,username: '=CMD',product_name: 'A,B',amount: 2.5,status: 'pending',created_at: '2026-11-11',notes: '@SUM(A1)'}]);
  assert.ok(result.includes('"\'=CMD"'));
  assert.ok(result.includes('"A,B"'));
  assert.ok(result.includes('"\'@SUM(A1)"'));
  assert.ok(result.includes('"2.50"'));
});
