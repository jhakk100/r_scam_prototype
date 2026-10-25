import assert from 'node:assert/strict';
import {parseText,maskSensitive,validateMessages} from './app/input.js';

const input='상대방: 첫 줄\n줄바꿈을 포함한 문장\n나: 답변';
assert.deepEqual(parseText(input),[
  {speaker:'상대방',text:'첫 줄\n줄바꿈을 포함한 문장'}, {speaker:'나',text:'답변'},
]);
assert.deepEqual(parseText('[상대방] [오후 1:30] 안녕하세요\r\n[나] [오후 1:31] 반가워요'),[
  {speaker:'상대방',text:'안녕하세요'}, {speaker:'나',text:'반가워요'},
]);
const plain='아직 화자가 없는 원문\nhttps://example.com/path\n14:30에 만나요';
assert.deepEqual(parseText(plain),[{speaker:'TEXT',text:plain}]);
const redacted=maskSensitive('전화 010-1234-5678, 메일 test@example.com, 비밀번호: abcd1234');
assert.equal(redacted.count,3);
assert(!redacted.text.includes('010-1234-5678') && !redacted.text.includes('abcd1234'));
const money='2026-10-24에 180만 원을 보내달래. 수익은 1,200만 원이래.';
assert.equal(maskSensitive(money).text,money);
assert.throws(()=>validateMessages([{speaker:'',text:'내용'}]));
assert.throws(()=>validateMessages([{speaker:'A',text:'x'.repeat(12001)}]));
assert.throws(()=>validateMessages(Array.from({length:97},()=>({speaker:'A',text:'내용'}))));
console.log('PASSED: speaker boundaries, multiline text, Kakao timestamps, privacy masking, amounts, input limits');
