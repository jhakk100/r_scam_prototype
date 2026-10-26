const $ = id => document.getElementById(id);
const escape = text => String(text).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const categories = ['의심 정황', '피해 경험', '정보 공유'];
const date = seconds => new Intl.DateTimeFormat('ko-KR', {dateStyle:'medium',timeStyle:'short'}).format(new Date(seconds*1000));
let page = 1, query = '', category = '', currentPost = null, generation = 0;
let feedback = '';
let activePage = null, commentTarget = null, commentPage = 1, commentTotal = 0, commentRequest = 0;

async function api(path, value) {
  const response = await fetch('/api/community/posts' + path, value === undefined ? {} : {
    method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(value),
  });
  const data = await response.json();
  if (!response.ok) throw Error(data.error || '요청을 완료하지 못했어요. 다시 시도해 주세요.');
  return data;
}
function showError(error, id='community-error') {
  $(id).textContent = error.message; $(id).hidden = false;
}
function go(path='') {
  const hash = '#community' + path;
  if (location.hash === hash) route(); else location.hash = hash;
}
function options(selected, all=false) {
  return (all ? '<option value="">전체 글</option>' : '') + categories.map(name => `<option${name === selected ? ' selected' : ''}>${name}</option>`).join('');
}
function meta(post) {
  return `<span class="board-category">${escape(post.category)}</span><span>${escape(post.author)}</span><time datetime="${new Date(post.created*1000).toISOString()}">${date(post.created)}</time>`;
}
async function list(ticket) {
  const data = await api(`?${new URLSearchParams({q:query,category,page})}`);
  if (ticket !== generation) return;
  const pages = Math.max(1, Math.ceil(data.total/data.page_size));
  if (page > pages) { page = pages; return list(ticket); }
  $('community-content').innerHTML = `
    <section class="card board-list-card">
      <form id="board-search" class="board-toolbar" role="search" aria-label="게시글 검색">
        <div><label class="visually-hidden" for="board-category">글 분류</label><select id="board-category">${options(category, true)}</select></div>
        <div class="board-search-field"><label class="visually-hidden" for="board-query">제목·내용 검색</label><input id="board-query" type="search" maxlength="100" placeholder="제목이나 내용으로 찾아보세요" value="${escape(query)}"><button class="button secondary" type="submit">검색</button></div>
      </form>
      <div class="board-list-heading"><h2>함께 나눈 이야기 <span class="muted">${data.total}</span></h2><span class="small muted">최근 작성 순</span></div>
      <div class="board-post-list">${data.posts.length ? data.posts.map(post => `<a class="board-post" href="#community/post/${post.id}"><div class="board-meta">${meta(post)}</div><h3>${escape(post.title)}</h3><p>${escape(post.preview)}</p><span class="board-read">이야기 읽기 →</span></a>`).join('') : `<div class="board-empty"><span aria-hidden="true">♡</span><h3>${query || category ? '아직 조건에 맞는 이야기가 없어요' : '첫 이야기를 기다리고 있어요'}</h3><p>${query || category ? '다른 검색어나 분류로 찾아보세요.' : '의심스러웠던 순간이나 겪었던 일을 남겨 주세요.<br>당신의 경험이 누군가에게 도움이 될 수 있어요.'}</p>${!query && !category ? '<button id="first-post" class="button secondary">첫 이야기 쓰기</button>' : ''}</div>`}</div>
      <div class="board-pagination"><button id="board-prev" class="button secondary" ${page === 1 ? 'disabled' : ''}>← 이전</button><span class="small">${page} / ${pages}</span><button id="board-next" class="button secondary" ${page >= pages ? 'disabled' : ''}>다음 →</button></div>
    </section>
    <p class="board-guidance">이름·연락처·계좌 등 개인을 식별할 수 있는 정보는 가려 주세요. 경험을 나누되 특정인을 범죄자로 단정하지 않아요.</p>`;
  $('board-search').onsubmit = event => { event.preventDefault(); query=$('board-query').value.trim(); category=$('board-category').value; page=1; route(); };
  $('board-category').onchange = () => $('board-search').requestSubmit();
  $('board-prev').onclick = () => { page--; route(); };
  $('board-next').onclick = () => { page++; route(); };
  if ($('first-post')) $('first-post').onclick = () => go('/write');
}
async function detail(ident, ticket) {
  const post = await api('/' + ident);
  if (ticket !== generation) return;
  currentPost = post;
  $('community-content').innerHTML = `<article class="card card-pad board-detail"><a class="text-link" href="#community">← 목록으로</a><div class="board-meta">${meta(post)}</div><h2 class="board-title" tabindex="-1">${escape(post.title)}</h2>${post.revision > 1 ? `<p class="small muted">수정 ${date(post.updated)}</p>` : ''}<div class="board-body">${escape(post.body)}</div><div class="board-detail-footer"><p class="small muted">직접 작성한 글은 글 비밀번호로 수정·삭제할 수 있어요.</p><div class="board-actions"><a class="button secondary" href="#community/edit/${post.id}">수정</a><button id="delete-post" class="button secondary">삭제</button></div></div></article>
    <section class="card card-pad comments-panel" aria-labelledby="comments-heading"><h2 id="comments-heading">댓글 <span id="comment-count" class="muted">0</span></h2><p id="comment-notice" class="board-feedback" role="status" hidden></p><p id="comment-error" class="error" role="alert" hidden></p><div id="comment-list" aria-busy="true"></div>
    <form id="comment-form" class="comment-form"><h3>댓글 남기기</h3><p class="small muted">가입 없이 이야기를 나눠요. 수정·삭제할 때 쓸 댓글 비밀번호를 기억해 주세요.</p>
    <label for="comment-body">댓글 내용</label><textarea id="comment-body" rows="4" maxlength="2000" placeholder="경험과 의견을 나눠 주세요. 이름·연락처 등 개인정보는 가려 주세요." required></textarea>
    <div class="comment-credentials"><div><label for="comment-author">닉네임</label><input id="comment-author" type="text" value="익명" maxlength="20" required autocomplete="off"></div><div><label for="comment-password">댓글 비밀번호</label><input id="comment-password" type="password" minlength="6" maxlength="128" placeholder="6자 이상" required autocomplete="off"></div><div><label for="comment-password-confirm">비밀번호 확인</label><input id="comment-password-confirm" type="password" minlength="6" maxlength="128" required autocomplete="off"></div></div>
    <label class="consent"><input id="comment-privacy" type="checkbox" required> 개인정보를 가렸으며 게시판 방문자에게 공개하는 데 동의합니다.</label><p id="comment-form-error" class="error" role="alert" hidden></p><div class="board-actions"><button class="button primary" type="submit">댓글 등록</button></div></form></section>`;
  $('delete-post').onclick = () => {
    $('delete-post-form').reset(); $('delete-post-error').hidden = true;
    $('delete-post-dialog').showModal();
  };
  document.querySelector('.board-title').focus({preventScroll:true});
  commentPage=1; commentTotal=0;
  $('comment-form').onsubmit = async event => {
    event.preventDefault(); $('comment-form-error').hidden=true;
    if ($('comment-password').value !== $('comment-password-confirm').value) return showError(Error('비밀번호 확인이 일치하지 않아요.'),'comment-form-error');
    const value = {author:$('comment-author').value,body:$('comment-body').value,password:$('comment-password').value,privacy_checked:$('comment-privacy').checked};
    const form = event.currentTarget, submit = event.submitter; submit.disabled=true;
    try {
      await api(`/${ident}/comments`,value);
      if (ticket !== generation) return;
      form.reset(); $('comment-notice').textContent='댓글을 남겼어요.'; $('comment-notice').hidden=false;
      await loadComments(ident,ticket,Math.max(1,Math.ceil((commentTotal+1)/20)));
    } catch (error) { if (ticket === generation) showError(error,'comment-form-error'); }
    finally { submit.disabled=false; }
  };
  await loadComments(ident,ticket,1);
}

async function loadComments(postId, ticket, page) {
  const request = ++commentRequest;
  $('comment-list').setAttribute('aria-busy','true'); $('comment-error').hidden=true;
  try {
    const data = await api(`/${postId}/comments?page=${page}`);
    if (ticket !== generation || request !== commentRequest) return;
    const pages = Math.max(1,Math.ceil(data.total/data.page_size));
    if (page > pages) return loadComments(postId,ticket,pages);
    commentPage=page; commentTotal=data.total; $('comment-count').textContent=data.total;
    $('comment-list').innerHTML = data.comments.length ? data.comments.map(comment => `<article class="community-comment"><div class="board-meta"><strong>${escape(comment.author)}</strong><time datetime="${new Date(comment.created*1000).toISOString()}">${date(comment.created)}</time>${comment.revision>1 ? '<span>수정됨</span>' : ''}</div><p class="comment-body">${escape(comment.body)}</p><div class="comment-actions"><button class="text-link" data-comment-action="edit" data-comment-id="${comment.id}" aria-label="${escape(comment.author)} 댓글 수정">수정</button><button class="text-link" data-comment-action="delete" data-comment-id="${comment.id}" aria-label="${escape(comment.author)} 댓글 삭제">삭제</button></div></article>`).join('') : '<p class="small muted comment-empty">아직 댓글이 없어요. 첫 의견을 남겨 주세요.</p>';
    if (pages > 1) $('comment-list').insertAdjacentHTML('beforeend',`<div class="board-pagination"><button id="comment-prev" class="button secondary" ${page===1?'disabled':''}>← 이전 댓글</button><span class="small">${page} / ${pages}</span><button id="comment-next" class="button secondary" ${page===pages?'disabled':''}>다음 댓글 →</button></div>`);
    for (const button of $('comment-list').querySelectorAll('[data-comment-action]')) {
      button.onclick = () => openCommentDialog(postId,data.comments.find(c=>c.id===button.dataset.commentId),button.dataset.commentAction,ticket);
    }
    if ($('comment-prev')) $('comment-prev').onclick = () => loadComments(postId,ticket,page-1);
    if ($('comment-next')) $('comment-next').onclick = () => loadComments(postId,ticket,page+1);
  } catch (error) { if (ticket === generation && request === commentRequest) showError(error,'comment-error'); }
  finally { if (ticket === generation && request === commentRequest) $('comment-list').setAttribute('aria-busy','false'); }
}
function openCommentDialog(postId, comment, action, ticket) {
  commentTarget={postId,comment,action,ticket};
  $('comment-change-form').reset(); $('comment-change-error').hidden=true;
  const editing=action==='edit';
  $('comment-dialog-title').textContent=editing?'댓글 수정':'댓글을 삭제할까요?';
  $('comment-edit-fields').hidden=!editing; $('comment-delete-note').hidden=editing;
  for (const id of ['comment-edit-author','comment-edit-body','comment-edit-privacy']) $(id).required=editing;
  $('comment-edit-author').value=comment.author; $('comment-edit-body').value=comment.body;
  $('submit-comment-change').textContent=editing?'수정한 댓글 저장':'댓글 삭제';
  $('comment-dialog').showModal();
}
$('cancel-comment-change').onclick = () => $('comment-dialog').close();
$('comment-dialog').addEventListener('close', () => { $('comment-change-form').reset(); commentTarget=null; });
$('comment-change-form').onsubmit = async event => {
  event.preventDefault(); const target=commentTarget; if (!target) return;
  $('comment-change-error').hidden=true; const submit=event.submitter; submit.disabled=true;
  const value={password:$('comment-change-password').value,revision:target.comment.revision,...(target.action==='edit'?{author:$('comment-edit-author').value,body:$('comment-edit-body').value,privacy_checked:$('comment-edit-privacy').checked}:{})};
  try {
    await api(`/${target.postId}/comments/${target.comment.id}/${target.action}`,value);
    if (target.ticket !== generation) return;
    $('comment-dialog').close(); $('comment-notice').textContent=target.action==='edit'?'댓글을 수정했어요.':'댓글을 삭제했어요.'; $('comment-notice').hidden=false;
    await loadComments(target.postId,target.ticket,commentPage);
  } catch (error) { if (target.ticket === generation) showError(error,'comment-change-error'); }
  finally { submit.disabled=false; }
};
async function editor(ident, ticket) {
  const post = ident ? await api('/' + ident) : null;
  if (ticket !== generation) return;
  $('community-content').innerHTML = `<section class="card card-pad board-editor"><a class="text-link" href="#community${post ? '/post/' + post.id : ''}">← ${post ? '글로 돌아가기' : '목록으로'}</a><h2 id="board-editor-heading" tabindex="-1">${post ? '이야기 수정하기' : '이야기 남기기'}</h2><p class="small muted">가입 없이 글을 남길 수 있어요. 수정·삭제할 때 사용할 글 비밀번호를 기억해 주세요.</p><form id="board-editor-form">
    <div class="board-form-row"><div><label for="post-category">글 분류</label><select id="post-category">${options(post?.category || categories[0])}</select></div><div><label for="post-author">닉네임</label><input id="post-author" type="text" maxlength="20" value="${escape(post?.author || '익명')}" required autocomplete="off"></div></div>
    <label for="post-title">제목</label><input id="post-title" type="text" maxlength="100" placeholder="어떤 일이 있었나요?" value="${escape(post?.title || '')}" required>
    <label for="post-body">내용</label><textarea id="post-body" rows="12" maxlength="8000" placeholder="상황과 대화의 흐름, 의심스러웠던 점을 적어 주세요. 이름·연락처·계좌 등은 가려 주세요." required>${escape(post?.body || '')}</textarea><p id="post-counter" class="small muted board-counter"></p>
    <div class="board-form-row"><div><label for="post-password">글 비밀번호${post ? ' 확인' : ''}</label><input id="post-password" type="password" minlength="6" maxlength="128" placeholder="${post ? '작성할 때 정한 비밀번호' : '6자 이상'}" required autocomplete="off"></div>${post ? '' : '<div><label for="post-password-confirm">비밀번호 확인</label><input id="post-password-confirm" type="password" minlength="6" maxlength="128" required autocomplete="off"></div>'}</div>
    <p class="small muted">비밀번호를 잊으면 복구할 수 없어요. 다른 서비스에서 쓰는 비밀번호는 피해주세요.</p>
    <label class="consent"><input id="post-privacy" type="checkbox" required> 본인과 상대방의 개인정보를 가렸으며, 이 글이 게시판 방문자에게 보이는 데 동의합니다.</label>
    <p id="post-form-error" class="error" role="alert" hidden></p><div class="board-actions"><a class="button secondary" href="#community${post ? '/post/' + post.id : ''}">취소</a><button type="submit" class="button primary">${post ? '수정한 글 저장' : '글 등록하기'}</button></div>
  </form></section>`;
  const count = () => { $('post-counter').textContent = `${$('post-body').value.length.toLocaleString()} / 8,000자`; };
  $('post-body').oninput = count; count();
  $('board-editor-heading').focus({preventScroll:true});
  $('board-editor-form').onsubmit = async event => {
    event.preventDefault(); $('post-form-error').hidden = true;
    if (!post && $('post-password').value !== $('post-password-confirm').value) return showError(Error('비밀번호 확인이 일치하지 않아요.'), 'post-form-error');
    const value = {category:$('post-category').value,author:$('post-author').value,title:$('post-title').value,body:$('post-body').value,password:$('post-password').value,privacy_checked:$('post-privacy').checked,...(post ? {revision:post.revision} : {})};
    const submit = event.submitter; submit.disabled = true; submit.textContent = '저장 중…';
    try {
      const saved = await api(post ? `/${post.id}/edit` : '', value);
      if (ticket !== generation) return;
      $('post-password').value = ''; if ($('post-password-confirm')) $('post-password-confirm').value = '';
      feedback = post ? '글을 수정했어요.' : '이야기를 남겼어요.'; go('/post/' + saved.id);
    } catch (error) { if (ticket === generation) showError(error, 'post-form-error'); }
    finally { submit.disabled=false; submit.textContent=post ? '수정한 글 저장' : '글 등록하기'; }
  };
}
async function route() {
  const ticket = ++generation;
  const isCommunity = location.hash === '#community' || location.hash.startsWith('#community/');
  const nextPage = isCommunity ? 'community' : 'analysis';
  if (nextPage !== activePage) {
    activePage=nextPage;
    window.dispatchEvent(new CustomEvent('site-page-change',{detail:{page:nextPage}}));
  }
  if ($('comment-dialog').open) $('comment-dialog').close();
  $('analysis-view').hidden = isCommunity; $('community-view').hidden = !isCommunity;
  for (const [id, active] of [['analysis-link',!isCommunity],['community-link',isCommunity]]) {
    $(id).classList.toggle('active', active);
    if (active) $(id).setAttribute('aria-current','page'); else $(id).removeAttribute('aria-current');
  }
  if (!isCommunity) return;
  $('community-error').hidden=true;
  $('community-notice').textContent=feedback; $('community-notice').hidden=!feedback; feedback='';
  $('community-write').hidden=location.hash.includes('/write') || location.hash.includes('/edit/');
  $('community-content').setAttribute('aria-busy','true');
  $('community-content').innerHTML='<p class="muted" role="status">이야기를 불러오고 있어요…</p>';
  currentPost = null;
  const path = location.hash.slice('#community'.length);
  try {
    if (!path || path === '/') await list(ticket);
    else if (path === '/write') await editor(null, ticket);
    else {
      const match = path.match(/^\/(post|edit)\/([a-f0-9]{32})$/);
      if (!match) throw Error('페이지를 찾을 수 없어요. 커뮤니티 탭을 눌러 목록으로 이동해 주세요.');
      if (match[1] === 'post') await detail(match[2], ticket); else await editor(match[2], ticket);
    }
  } catch (error) { if (ticket === generation) { $('community-content').replaceChildren(); showError(error); } }
  finally { if (ticket === generation) $('community-content').setAttribute('aria-busy','false'); }
}
$('community-write').onclick = () => go('/write');
$('cancel-delete-post').onclick = () => $('delete-post-dialog').close();
$('delete-post-dialog').addEventListener('close', () => { $('delete-password').value=''; });
$('delete-post-form').onsubmit = async event => {
  event.preventDefault(); if (!currentPost) return;
  const submit = event.submitter; submit.disabled=true; $('delete-post-error').hidden=true;
  try {
    await api(`/${currentPost.id}/delete`, {password:$('delete-password').value,revision:currentPost.revision});
    $('delete-post-dialog').close(); feedback='글을 삭제했어요.'; go();
  } catch (error) { showError(error,'delete-post-error'); }
  finally { submit.disabled=false; }
};
window.addEventListener('hashchange', route);
route();
