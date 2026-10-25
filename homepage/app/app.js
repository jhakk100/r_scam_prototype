import {parseText, maskSensitive, validateMessages} from './input.js';

const $ = id => document.getElementById(id);
const escape = text => String(text).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number = n => Number(n).toFixed(1);
const levelText = {HIGH:'주의가 필요한 대화', LOW:'위험 신호가 낮은 대화', UNKNOWN:'판단이 불확실한 대화'};
const levelLabel = {HIGH:'주의', LOW:'낮음', UNKNOWN:'판단 유보'};
let step = 0, busy = false, messages = [], images = [], examples = [], config = null, lastResult = null;

function showError(error) {
  $('error').textContent = error?.message || String(error);
  $('error').hidden = false;
  $('error').scrollIntoView({behavior:'smooth', block:'center'});
}
function clearError() { $('error').hidden = true; }
function changeStep(value) {
  step = value;
  for (const item of document.querySelectorAll('[data-step]')) {
    const n = Number(item.dataset.step);
    item.classList.toggle('current', n === value);
    item.classList.toggle('complete', n < value);
    if (n === value) item.setAttribute('aria-current', 'step');
    else item.removeAttribute('aria-current');
  }
  $('input-workspace').hidden = value === 2 || busy;
  $('upload-panel').hidden = value !== 0;
  $('review-panel').hidden = value !== 1;
  $('result-panel').hidden = value !== 2;
  $('progress-panel').hidden = !busy;
  if (value === 1 && !busy) {
    requestAnimationFrame(() => $('review-panel').scrollIntoView({block:'start'}));
  }
}
function setTab(mode) {
  for (const name of ['text','image']) {
    $(`${name}-tab`).setAttribute('aria-selected', String(name === mode));
    $(`${name}-tab`).tabIndex = name === mode ? 0 : -1;
    $(`${name}-panel`).hidden = name !== mode;
  }
  $('review-button').disabled = busy || mode === 'image';
}
for (const mode of ['text','image']) {
  $(`${mode}-tab`).onclick = () => setTab(mode);
  $(`${mode}-tab`).onkeydown = event => {
    if (['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) {
      event.preventDefault();
      const next = event.key === 'Home' ? 'text' : event.key === 'End' ? 'image' : mode === 'text' ? 'image' : 'text';
      setTab(next); $(`${next}-tab`).focus();
    }
  };
}

async function getJSON(url, options = {}) {
  const response = await fetch(url, {...options, signal: AbortSignal.timeout(15000), cache:'no-store'});
  const data = await response.json();
  if (!response.ok) throw Error(data.error || '서버 요청에 실패했습니다.');
  return data;
}
async function refreshStatus() {
  try {
    config = await getJSON('/api/status');
    if (config.app !== 'maeum-check-final-v4') throw Error('마음체크_시작.cmd로 홈페이지를 열어 주세요.');
    if (!config.ocr_available) $('ocr-status').textContent = '이미지에서 글자를 읽을 수 없어요. 텍스트를 직접 입력해 주세요.';
  } catch (error) {
    showError(Error('연결할 수 없어요. 마음체크_시작.cmd로 홈페이지를 다시 열어 주세요.'));
  }
}
refreshStatus();

async function loadExample(index) {
  if (busy) return;
  try {
    clearError();
    if (!examples.length) examples = await getJSON('/api/examples');
    $('conversation').value = examples[index].messages.map(m => `${m.speaker}: ${m.text}`).join('\n');
    setTab('text'); $('conversation').focus();
  } catch (error) { showError(error); }
}
$('scam-example').onclick = () => loadExample(0);
$('normal-example').onclick = () => loadExample(1);

function renderEditor() {
  const scrollTop = $('messages-editor').scrollTop;
  $('messages-editor').replaceChildren();
  messages.forEach((message, index) => {
    const row = document.createElement('div'); row.className = 'message-row';
    const head = document.createElement('div'); head.className = 'message-row-head';
    const label = document.createElement('label'); label.textContent = `${index + 1}. 화자`;
    const speaker = document.createElement('input'); speaker.type = 'text'; speaker.maxLength = 40; speaker.value = message.speaker;
    speaker.setAttribute('aria-label', `${index + 1}번 발화 화자`);
    speaker.oninput = () => { message.speaker = speaker.value; invalidateConsent(); };
    label.append(speaker);
    const remove = document.createElement('button'); remove.className = 'delete-message'; remove.textContent = '삭제';
    remove.setAttribute('aria-label', `${index + 1}번 발화 삭제`);
    remove.onclick = () => { messages.splice(index,1); invalidateConsent(); renderEditor(); };
    head.append(label, remove);
    const text = document.createElement('textarea'); text.rows = 2; text.value = message.text;
    text.setAttribute('aria-label', `${index + 1}번 발화 내용`);
    text.oninput = () => { message.text = text.value; invalidateConsent(); };
    row.append(head, text); $('messages-editor').append(row);
  });
  $('message-count').textContent = `${messages.length}개 발화`;
  $('messages-editor').scrollTop = scrollTop;
}
function invalidateConsent() { $('consent').checked = false; $('analyze-button').disabled = true; }
$('consent').onchange = () => { $('analyze-button').disabled = !$('consent').checked; };
$('add-message').onclick = () => {
  if (messages.length >= 96) return showError(Error('발화는 최대 96개까지 입력할 수 있어요.'));
  messages.push({speaker:'', text:''}); invalidateConsent(); renderEditor();
  $('messages-editor').lastElementChild.querySelector('input').focus();
};
$('review-button').onclick = () => {
  try {
    clearError();
    if ($('conversation').value.length > 16000) throw Error('대화를 조금 줄여 주세요.');
    const masked = maskSensitive($('conversation').value);
    messages = validateMessages(parseText(masked.text));
    $('mask-note').textContent = `연락처·계좌번호 등 ${masked.count}곳을 자동으로 가렸어요. 이름·주소 등 남은 정보는 직접 수정해 주세요.`;
    invalidateConsent(); renderEditor(); changeStep(1); $('messages-editor').scrollTop=0; $('review-heading').focus();
  } catch (error) { showError(error); }
};
$('back-button').onclick = () => {
  $('conversation').value = messages.map(m => `${m.speaker}: ${m.text}`).join('\n');
  invalidateConsent(); clearError(); setTab('text'); changeStep(0); $('conversation').focus();
};

function clearImages() {
  for (const image of images) URL.revokeObjectURL(image.url);
  images = []; $('images').value = ''; renderImages();
}
function renderImages() {
  $('image-list').replaceChildren();
  images.forEach((image, index) => {
    const item = document.createElement('div'); item.className = 'image-thumb';
    const img = document.createElement('img'); img.src = image.url; img.alt = `${index+1}번째 대화 이미지`;
    const button = document.createElement('button'); button.textContent = '×'; button.setAttribute('aria-label', `${index+1}번째 이미지 제거`);
    button.onclick = () => { URL.revokeObjectURL(image.url); images.splice(index,1); renderImages(); };
    item.append(img, button); $('image-list').append(item);
  });
  $('extract-button').disabled = !images.length || busy;
}
async function addImages(files) {
  if (busy) return;
  try {
    clearError();
    if (images.length + files.length > 4) throw Error('이미지는 최대 4장까지 선택해 주세요.');
    for (const file of files) {
      if (!['image/png','image/jpeg','image/webp'].includes(file.type)) throw Error('PNG, JPG, WEBP 이미지를 선택해 주세요.');
      if (file.size > 10*1024*1024) throw Error('이미지는 장당 10MB까지 선택할 수 있어요.');
      const bitmap = await createImageBitmap(file);
      const pixels = bitmap.width * bitmap.height; bitmap.close();
      if (pixels > 24000000) throw Error('이미지가 너무 커요. 2,400만 화소 이하로 줄여 주세요.');
    }
    images.push(...Array.from(files, file => ({file, url:URL.createObjectURL(file)})));
    renderImages();
  } catch (error) { showError(error); }
  $('images').value = '';
}
$('images').onchange = () => addImages(Array.from($('images').files));
$('dropzone').ondragover = event => { event.preventDefault(); $('dropzone').classList.add('dragging'); };
$('dropzone').ondragleave = () => $('dropzone').classList.remove('dragging');
$('dropzone').ondrop = event => { event.preventDefault(); $('dropzone').classList.remove('dragging'); addImages(Array.from(event.dataTransfer.files)); };
$('extract-button').onclick = async () => {
  if (busy || !images.length) return;
  if (!config?.ocr_available) return showError(Error('이미지에서 글자를 읽을 수 없어요. 텍스트를 직접 입력해 주세요.'));
  busy = true; $('extract-button').disabled = true; $('review-button').disabled = true;
  $('images').disabled = true;
  for (const button of $('image-list').querySelectorAll('button')) button.disabled = true;
  let worker;
  try {
    clearError(); $('ocr-status').textContent = '한국어·영어 글자 인식을 준비하고 있어요.';
    const {default:tesseract} = await import('/_next/static/chunks/src-DXZWLGLI.js');
    worker = await tesseract.createWorker(['kor','eng'], 1, {
      workerPath:'/ocr/worker.min.js', corePath:'/ocr', langPath:'/ocr',
      workerBlobURL:false, cacheMethod:'none',
      logger: log => { if (log.status === 'recognizing text') $('ocr-status').textContent = `글자를 읽고 있어요. ${Math.round(log.progress*100)}%`; },
    });
    await worker.setParameters({preserve_interword_spaces:'1'});
    const output = [];
    for (let i=0; i<images.length; i++) {
      const bitmap = await createImageBitmap(images[i].file);
      const scale = Math.min(2, 2400 / Math.max(bitmap.width,bitmap.height));
      const canvas = document.createElement('canvas'); canvas.width = Math.round(bitmap.width*scale); canvas.height = Math.round(bitmap.height*scale);
      const context = canvas.getContext('2d'); context.fillStyle='white'; context.fillRect(0,0,canvas.width,canvas.height); context.drawImage(bitmap,0,0,canvas.width,canvas.height); bitmap.close();
      let timer;
      const result = await Promise.race([
        worker.recognize(canvas),
        new Promise((_, reject) => { timer=setTimeout(() => reject(Error('글자 인식 시간이 초과됐어요. 더 작은 이미지로 다시 시도해 주세요.')),180000); }),
      ]).finally(() => { clearTimeout(timer); canvas.width=canvas.height=0; });
      output.push(result.data.text.trim());
    }
    if (!output.some(Boolean)) throw Error('인식한 글자가 없어요. 선명한 이미지나 텍스트를 사용해 주세요.');
    $('conversation').value = output.join('\n\n');
    setTab('text'); $('ocr-status').textContent = '문장을 추출했어요. 텍스트와 화자를 확인해 주세요.';
    $('conversation').focus();
  } catch (error) { showError(error); $('ocr-status').textContent = '인식을 완료하지 못했어요. 텍스트로 직접 입력할 수 있어요.'; }
  finally {
    if (worker) await worker.terminate();
    busy=false; $('images').disabled=false; $('review-button').disabled=!$('image-panel').hidden; renderImages();
  }
};

$('analyze-button').onclick = async () => {
  if (busy || !$('consent').checked) return;
  try {
    validateMessages(messages); clearError(); busy=true; changeStep(1);
    $('job-status').textContent = '분석을 시작하고 있어요.'; $('progress-heading').focus();
    const {job} = await getJSON('/api/analyze', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({messages})});
    let failures = 0;
    const started = Date.now();
    while (true) {
      await new Promise(resolve => setTimeout(resolve,1200));
      let status;
      try { status = await getJSON(`/api/jobs/${job}`); failures=0; }
      catch (error) {
        if (++failures >= 4) throw Error('분석 서버와 연결이 끊겼어요. 잠시 뒤 다시 시도해 주세요.');
        $('job-status').textContent='서버에 다시 연결하고 있어요.'; continue;
      }
      if (status.state === 'error') throw Error(status.detail);
      if (status.state === 'done') {
        lastResult=status.result; busy=false; renderResult(lastResult); changeStep(2);
        $('result-heading').focus(); clearImages(); break;
      }
      $('job-status').textContent = `${status.state === 'loading' ? '분석을 준비하고 있어요.' : '대화 내용을 살펴보고 있어요.'} (${Math.floor((Date.now()-started)/1000)}초)`;
    }
  } catch (error) { busy=false; changeStep(1); showError(error); }
};

function bubbles(items) {
  return items.map(m => `<div class="bubble"><strong>${escape(m.speaker)}</strong>${escape(m.text)}</div>`).join('');
}
function renderResult(data) {
  const f=data.final, color={HIGH:'#b67b4e',LOW:'#54877a',UNKNOWN:'#7785aa'}[f.level];
  const description={HIGH:'주의가 필요한 대화예요. 앞뒤 맥락을 다시 살펴보고, 금전이나 개인정보를 요구받았다면 신중하게 확인해 주세요.',LOW:'현재 대화의 위험 지수는 낮은 구간에 있어요. 낮은 점수가 상대방의 안전성을 보장하지는 않아요.',UNKNOWN:'현재 대화만으로는 판단이 어려워요. 앞뒤 맥락을 더 확인해 주세요.'}[f.level];
  $('result-panel').innerHTML = `
    <section class="card result-top" style="--score:${f.risk_score};--risk-color:${color}">
      <div class="gauge" role="img" aria-label="위험 지수 ${number(f.risk_score)}점, ${escape(levelText[f.level])}"><div class="gauge-text"><p>위험 지수</p><div class="gauge-number">${number(f.risk_score)}<span> / 100</span></div><b>${escape(levelLabel[f.level])}</b></div></div>
      <div><span class="risk-badge">대화 분석 결과</span><h2 id="result-heading" class="result-title" tabindex="-1">${escape(levelText[f.level])}</h2><p class="result-summary">${escape(description)}</p><p class="small muted">점수는 실제 사기 확률이 아닌 참고 정보예요.</p></div>
    </section>
    <div class="result-grid"><div class="result-stack">
      <section class="card card-pad"><div class="section-heading"><h2>비슷한 대화 사례</h2></div><p class="small muted">사례를 펼쳐 대화 내용을 비교해 보세요. 비슷한 표현이 있어도 실제 상황은 다를 수 있어요.</p>
        <div class="case-list">${data.neighbors.map((h,i) => `<details><summary>${i+1}. 참고 사례 <span class="case-label">${h.label==='SCAM'?'스캠 사례':'일반 사례'}</span></summary><div class="case-messages">${bubbles(h.messages)}</div></details>`).join('')}</div>
      </section>
      <section class="card card-pad"><h2>분석한 대화</h2><details><summary>입력한 대화 보기</summary><div class="case-messages">${bubbles(messages)}</div></details></section>
    </div><aside class="result-stack">
      <section class="card aside-card"><h3>결과를 읽는 방법</h3><dl class="facts"><div><dt>낮음</dt><dd>40점 미만</dd></div><div><dt>판단 유보</dt><dd>40~60점</dd></div><div><dt>주의</dt><dd>60점 초과</dd></div></dl><p class="small muted" style="margin-top:16px">분석 결과만으로 상대방을 단정하지 말고, 대화의 맥락과 실제 상황을 함께 확인해 주세요.</p></section>
    </aside></div>
    <div class="result-actions"><button id="download-result" class="button secondary">결과 저장</button><button id="edit-result" class="button secondary">문장 수정하기</button><button id="new-analysis" class="button primary">새 대화 분석 →</button></div>`;
  $('download-result').onclick = () => {
    const text = `마음체크 분석 결과\n\n위험 지수: ${number(f.risk_score)} / 100\n${levelText[f.level]}\n${description}\n\n점수는 실제 사기 확률이 아닌 참고 정보입니다.\n\n분석한 대화\n${messages.map(m => `${m.speaker}: ${m.text}`).join('\n')}`;
    const blob = new Blob(['\uFEFF',text],{type:'text/plain;charset=utf-8'});
    const url = URL.createObjectURL(blob), link=document.createElement('a');
    link.href=url; link.download='마음체크_분석결과.txt'; link.click(); setTimeout(() => URL.revokeObjectURL(url),1000);
  };
  $('edit-result').onclick = () => { invalidateConsent(); changeStep(1); $('review-heading').focus(); };
  $('new-analysis').onclick = () => { messages=[]; lastResult=null; $('result-panel').replaceChildren(); $('conversation').value=''; invalidateConsent(); clearError(); changeStep(0); setTab('text'); $('conversation').focus(); };
}

function showInfo(title, html) { $('dialog-title').textContent=title; $('dialog-content').innerHTML=html; $('info-dialog').showModal(); }
$('about-button').onclick = () => showInfo('분석 기준', '<p>입력한 대화의 흐름과 비슷한 사례를 참고해 위험 지수를 보여드려요.</p><p>40점 미만은 낮음, 40~60점은 판단 유보, 60점 초과는 주의 구간이에요.</p><p>점수는 실제 사기 확률이 아니며, 상대방의 안전성을 보장하지 않아요. 대화의 앞뒤 맥락과 실제 상황을 함께 확인해 주세요.</p>');
$('privacy-button').onclick = () => showInfo('개인정보 처리 안내', '<p>이미지와 대화는 이 컴퓨터에서 처리해요. 확인한 대화만 분석에 사용하며, 파일로 자동 저장하지 않아요.</p><p>결과는 약 15분 뒤 정리돼요. 직접 보관하려면 결과 저장 버튼을 눌러 주세요.</p><p>일부 연락처 등은 자동으로 가려지지만, 이름·주소 등 남은 개인정보는 직접 확인해 주세요.</p>');
$('close-dialog').onclick = () => $('info-dialog').close();
window.addEventListener('beforeunload', event => { if (busy) { event.preventDefault(); event.returnValue=''; } });
