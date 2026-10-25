// The review screen makes every inferred speaker boundary editable before inference.
export function parseText(text) {
  const messages = [];
  let current = null;
  for (const line of text.replace(/\r\n?/g, '\n').split('\n')) {
    const match = line.match(/^\s*\[([^\]\n]{1,40})\]\s*\[(?:오전|오후|AM|PM)?\s*\d{1,2}:\d{2}[^\]]*\]\s?(.*)$/)
      || line.match(/^\s*([^:\n]{1,40}):[ \t]+(.*)$/);
    if (match && !/^https?$|^\d{1,2}$/i.test(match[1].trim())) {
      if (current) messages.push(current);
      current = {speaker: match[1].trim(), text: match[2]};
    } else if (current) {
      current.text += '\n' + line;
    } else if (line.trim()) {
      current = {speaker: 'TEXT', text: line};
    }
  }
  if (current) messages.push(current);
  return messages.filter(m => m.text.trim());
}

export function maskSensitive(text) {
  let count = 0;
  const patterns = [
    [/(?<!\d)\d{6}\s*-?\s*[1-8]\d{6}(?!\d)/g, '주민등록번호'],
    [/\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi, '이메일'],
    [/(?<!\d)(?:\+82[ -]?(?:10|2|[3-6]\d)|0(?:1[016789]|2|[3-6]\d))[ -]?\d{3,4}[ -]?\d{4}(?!\d)/g, '전화번호'],
    [/(?<!\d)\d{10,16}(?!\d)/g, '긴 숫자'],
    [/(?<!\d)(?:\d{2,6}[- ]\d{2,6}[- ]\d{2,7}(?:[- ]\d{1,4})?)(?!\d)/g, '계좌번호 의심'],
  ];
  let value = text;
  for (const [pattern, name] of patterns) {
    value = value.replace(pattern, match => {
      if (/^20\d{2}[- ](?:0?[1-9]|1[0-2])[- ](?:0?[1-9]|[12]\d|3[01])$/.test(match)) return match;
      count++;
      return `[${name} 가림]`;
    });
  }
  value = value.replace(/((?:인증번호|비밀번호|OTP|password|verification code)\s*[:：=]?\s*)([A-Za-z0-9!@#$%^&*]{4,})/gi,
    (_, prefix) => { count++; return `${prefix}[인증정보 가림]`; });
  return {text: value, count};
}

export function validateMessages(messages) {
  if (!messages.length || messages.length > 96) throw Error('발화는 1~96개까지 입력해 주세요.');
  if (messages.some(m => !m.speaker.trim() || m.speaker.length > 40 || !m.text.trim()))
    throw Error('각 발화의 화자와 문장을 모두 입력해 주세요.');
  if (messages.reduce((n, m) => n + m.text.length, 0) > 12000)
    throw Error('대화는 12,000자 이내로 입력해 주세요. 자동으로 자르지 않습니다.');
  return messages;
}
