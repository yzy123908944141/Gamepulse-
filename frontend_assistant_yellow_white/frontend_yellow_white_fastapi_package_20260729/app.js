import { characterCatalog, scriptLines, violations } from './mockData.js?v=20260729_db_panel_v1';

const apiParam = new URLSearchParams(window.location.search).get('api');
const FASTAPI_BASE_URL = apiParam
  ?? window.GAMERPULSE_API_BASE
  ?? (window.location.port === '8000' ? window.location.origin : 'http://127.0.0.1:8000');


const scriptEditor = document.querySelector('#scriptEditor');
const suggestionList = document.querySelector('#suggestionList');
const tooltip = document.querySelector('#violationTooltip');
const sourceOverlay = document.querySelector('#sourceOverlay');
const dialogTitle = document.querySelector('#dialogTitle');
const sourceList = document.querySelector('#sourceList');
const closeDialogButton = document.querySelector('#closeDialogButton');
const exportReportButton = document.querySelector('#exportReportButton');
const networkOverlay = document.querySelector('#networkOverlay');
const networkBanner = document.querySelector('#networkBanner');
const networkMessage = document.querySelector('#networkMessage');
const retryNetworkButton = document.querySelector('#retryNetworkButton');
const dismissNetworkButton = document.querySelector('#dismissNetworkButton');
const customCursor = document.querySelector('#customCursor');
const viewButtons = document.querySelectorAll('[data-view-target]');
const moduleViews = document.querySelectorAll('.module-view');
const pageButtons = document.querySelectorAll('[data-page-target]');
const pageScreens = document.querySelectorAll('.page-screen');
const violationCount = document.querySelector('#violationCount');
const totalCharCount = document.querySelector('#totalCharCount');
const violationRatio = document.querySelector('#violationRatio');
const ratioMeterFill = document.querySelector('#ratioMeterFill');
const versionTree = document.querySelector('#versionTree');
const characterSearchForm = document.querySelector('#characterSearchForm');
const characterSearchInput = document.querySelector('#characterSearchInput');
const characterSearchList = document.querySelector('#characterSearchList');
const characterSearchStatus = document.querySelector('#characterSearchStatus');
const selectedCharacterName = document.querySelector('#selectedCharacterName');
const portraitPlaceholder = document.querySelector('#portraitPlaceholder');
const selectedCharacterMeta = document.querySelector('#selectedCharacterMeta');
const characterRiskPanel = document.querySelector('#characterRiskPanel');
const characterKeywordPanel = document.querySelector('#characterKeywordPanel');
const characterStoryPanel = document.querySelector('#characterStoryPanel');
const assistantMessages = document.querySelector('#assistantMessages');
const assistantForm = document.querySelector('#assistantForm');
const assistantInput = document.querySelector('#assistantInput');
const agentFlowStatus = document.querySelector('#agentFlowStatus');
const agentFlowSteps = document.querySelectorAll('[data-agent-step]');
const agentFlow = document.querySelector('#agentFlow');
const operationLog = document.querySelector('#operationLog');
const databasePanel = document.querySelector('#databasePanel');

let activeViolationId = 'v1';
let currentCharacterId = null;
let lastFailedApiPath = null;
let assistantSessionId = null;
let assistantBusy = false;


function formatBytes(bytes = 0) {
  const value = Number(bytes || 0);
  if (value >= 1024 * 1024) return `${(value / 1024 / 1024).toFixed(2)} MB`;
  if (value >= 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${value} B`;
}

function renderDatabaseSummary(payload = {}) {
  const databases = Array.isArray(payload.databases) ? payload.databases : [];
  if (!databasePanel) return;
  if (!databases.length) {
    databasePanel.innerHTML = '<div class="database-panel__empty">暂无数据库摘要。</div>';
    return;
  }
  databasePanel.innerHTML = databases.map((db) => {
    const status = db.exists ? 'ONLINE' : 'MISSING';
    const statusClass = db.exists ? 'is-online' : 'is-missing';
    const tables = Array.isArray(db.tables) && db.tables.length
      ? db.tables.map((table) =>
          '<div class="database-table-row">' +
            '<span>' + escapeHtml(table.name) + '</span>' +
            '<strong>' + escapeHtml(table.rows) + '</strong>' +
            '<small>' + escapeHtml((table.columns || []).join(' / ')) + '</small>' +
          '</div>'
        ).join('')
      : '<div class="database-panel__empty">无可展示表。</div>';
    return '<article class="database-card">' +
      '<div class="database-card__head">' +
        '<span class="database-card__name">' + escapeHtml(db.label || db.key || 'database') + '</span>' +
        '<span class="database-card__status ' + statusClass + '">' + status + '</span>' +
      '</div>' +
      '<p>' + escapeHtml(db.purpose || '') + '</p>' +
      '<div class="database-card__meta">' +
        '<span>size=' + escapeHtml(formatBytes(db.size_bytes)) + '</span>' +
        '<span>tables=' + escapeHtml((db.tables || []).length) + '</span>' +
      '</div>' +
      '<code>' + escapeHtml(db.path || '') + '</code>' +
      '<div class="database-table-list">' + tables + '</div>' +
    '</article>';
  }).join('');
}

async function loadDatabaseSummary() {
  if (!databasePanel) return;
  try {
    const payload = await fetchFastApi('/api/db/summary', { timeoutMs: 8000 });
    renderDatabaseSummary(payload);
  } catch (error) {
    console.warn('Failed to load database summary:', error);
    databasePanel.innerHTML = '<div class="database-panel__empty">数据库摘要读取失败，请确认后端服务已启动。</div>';
  }
}
function getMajorVersion(version) {
  const major = String(version).split('.')[0];
  return `${major}.0`;
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}


function getOperationTime() {
  return new Date().toLocaleTimeString('zh-CN', { hour12: false });
}

function appendOperationLog(tag, text, type = 'request') {
  if (!operationLog) return;
  const item = document.createElement('div');
  item.className = `operation-log__item operation-log__item--${type}`;
  item.innerHTML = `
    <span class="operation-log__time">${escapeHtml(getOperationTime())}</span>
    <span class="operation-log__tag">${escapeHtml(tag)}</span>
    <span class="operation-log__text">${escapeHtml(String(text || '')).replaceAll('\n', '<br>')}</span>
  `;
  operationLog.appendChild(item);
  while (operationLog.children.length > 80) operationLog.removeChild(operationLog.firstElementChild);
  operationLog.scrollTop = operationLog.scrollHeight;
}

function logRuntimeEvent(event = {}) {
  const type = event.type || 'status';
  if (type.startsWith('agent_')) appendOperationLog('AGENT', formatRuntimeEvent(event), 'agent');
  else if (type.startsWith('tool_')) appendOperationLog('TOOL', formatRuntimeEvent(event), type === 'tool_error' ? 'error' : 'tool');
  else appendOperationLog('EVENT', formatRuntimeEvent(event), 'response');
}

function summarizeFinalPayload(payload = {}) {
  const success = payload.success === false ? '失败' : '成功';
  const agents = payload.called_agents?.length ? payload.called_agents.join(' -> ') : 'none';
  const tools = payload.called_tools?.length ? payload.called_tools.join(' -> ') : 'none';
  const answerLength = String(payload.answer || '').length;
  const error = payload.error ? `；error=${payload.error}` : '';
  return `接口最终返回：${success}；answer_chars=${answerLength}；agents=${agents}；tools=${tools}${error}`;
}
function compareVersionLabel(a, b) {
  const normalize = (value) => String(value).replace('x', '99').split('.').map(Number);
  const [aMajor, aMinor] = normalize(a);
  const [bMajor, bMinor] = normalize(b);
  return aMajor - bMajor || aMinor - bMinor;
}


function normalizeRiskWarnings(items = []) {
  return (Array.isArray(items) ? items : []).map((item) => ({
    level: item.level ?? item.risk_level ?? item.riskLevel ?? '未知风险',
    title: item.title ?? '未命名风险',
    description: item.description ?? item.desc ?? '',
  }));
}

function normalizeKeywords(items = []) {
  const sentimentMap = {
    positive: '正向',
    negative: '负向',
    neutral: '中性',
    pos: '正向',
    neg: '负向',
    neu: '中性',
  };

  return (Array.isArray(items) ? items : []).map((item) => {
    const rawSentiment = item.sentiment ?? item.polarity ?? item.tone ?? '中性';
    const sentiment = sentimentMap[String(rawSentiment).toLowerCase()] ?? rawSentiment;
    return {
      keyword: item.keyword ?? item.word ?? item.text ?? '未命名关键词',
      weight: item.weight ?? item.score ?? item.value ?? 0,
      sentiment,
    };
  });
}

function normalizeCommentItems(payload) {
  const rawComments = Array.isArray(payload) ? payload : payload?.comments ?? [];
  return rawComments.map((comment) => ({
    id: comment.id,
    platform: comment.platform ?? comment.source ?? '未知平台',
    content: comment.content ?? '',
    publishDate: comment.publishDate ?? comment.publish_date ?? '',
    url: comment.url ?? comment.source_url ?? '',
  }));
}

function normalizeDiagnosisPayload(payload = {}) {
  const scores = payload.scores ?? {};
  return {
    scores: {
      character: Math.round(Number(scores.character ?? scores.character_score ?? payload.character_score ?? 0)),
      gameplay: Math.round(Number(scores.gameplay ?? scores.gameplay_score ?? payload.gameplay_score ?? 0)),
      systempain: Math.round(Number(scores.systempain ?? scores.system_pain_score ?? payload.system_pain_score ?? 0)),
    },
    riskWarnings: normalizeRiskWarnings(payload.riskWarnings ?? payload.risk_warnings ?? []),
    characterKeywords: normalizeKeywords(payload.characterKeywords ?? payload.word_cloud_data ?? []),
    associatedCommentIds: payload.associatedCommentIds ?? payload.associated_comment_ids ?? [],
    personalStory: payload.personalStory ?? payload.personal_story ?? payload.story ?? payload.profile_story ?? payload.character_story,
    analysisDate: payload.analysisDate ?? payload.analysis_date,
  };
}

function showNetworkNotice(message, path = null, { modal = false } = {}) {
  lastFailedApiPath = path;
  const text = message || '后台连接暂时不可用，已切换到本地兜底数据。';

  if (networkBanner) {
    networkBanner.textContent = text;
    networkBanner.hidden = false;
    window.clearTimeout(showNetworkNotice.bannerTimer);
    showNetworkNotice.bannerTimer = window.setTimeout(() => {
      networkBanner.hidden = true;
    }, 3600);
  }

  if (modal && networkOverlay) {
    if (networkMessage) networkMessage.textContent = text;
    networkOverlay.hidden = false;
  }
}

function hideNetworkNotice() {
  if (networkOverlay) networkOverlay.hidden = true;
  if (networkBanner) networkBanner.hidden = true;
}

async function fetchFastApi(path, options = {}) {
  const timeoutMs = options.timeoutMs ?? 5200;
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(`${FASTAPI_BASE_URL}${path}`, {
      cache: 'no-store',
      signal: controller.signal,
      ...options.fetchOptions,
    });
    if (!response.ok) throw new Error(`FastAPI ${response.status}: ${path}`);
    hideNetworkNotice();
    return response.json();
  } catch (error) {
    const reason = error.name === 'AbortError' ? '请求超时' : '连接失败';
    showNetworkNotice(`${reason}：FastAPI 后端暂时不可用，页面已启用演示兜底。`, path, { modal: options.modal ?? false });
    throw error;
  } finally {
    window.clearTimeout(timer);
  }
}

async function loadCharacterDiagnosisFromFastApi(character) {
  if (!character || character.fastApiLoaded) return character;

  try {
    const payload = await fetchFastApi(`/api/diagnosis?character_id=${encodeURIComponent(character.id)}`);
    if (payload && !payload.error && payload.analysis_id !== null) {
      const normalized = normalizeDiagnosisPayload(payload);
      character.scores = normalized.scores;
      character.riskWarnings = normalized.riskWarnings;
      character.characterKeywords = normalized.characterKeywords;
      character.associatedCommentIds = normalized.associatedCommentIds;
      if (normalized.personalStory) character.personalStory = normalized.personalStory;
      character.analysisDate = normalized.analysisDate;
    }
    character.fastApiLoaded = true;
  } catch (error) {
    console.warn('Using built-in character fallback because FastAPI diagnosis failed:', error);
    character.fastApiError = true;
  }

  return character;
}

function normalizeSearchText(value) {
  return String(value ?? '').trim().toLowerCase();
}

function renderCharacterSearchOptions() {
  if (!characterSearchList) return;
  characterSearchList.innerHTML = characterCatalog
    .map((character) => `<option value="${escapeHtml(character.name)}">${escapeHtml(character.version)}</option>`)
    .join('');
}

function setCharacterSearchStatus(message, mode = 'idle') {
  if (!characterSearchStatus) return;
  characterSearchStatus.textContent = message;
  characterSearchStatus.dataset.mode = mode;
}

function findCharacterBySearch(query) {
  const normalizedQuery = normalizeSearchText(query);
  if (!normalizedQuery) return null;

  const candidates = characterCatalog.map((character) => ({
    character,
    name: normalizeSearchText(character.name),
  }));

  return candidates.find((item) => item.name === normalizedQuery)?.character
    ?? candidates.find((item) => item.name.startsWith(normalizedQuery))?.character
    ?? candidates.find((item) => item.name.includes(normalizedQuery))?.character
    ?? null;
}

async function jumpToCharacterByName(query) {
  const character = findCharacterBySearch(query);
  if (!character) {
    setCharacterSearchStatus('未找到对应角色，请检查名称或尝试输入更短关键词。', 'error');
    characterSearchInput?.focus();
    return;
  }

  await selectCharacter(character.id, { scrollToDetail: true });
  if (characterSearchInput) characterSearchInput.value = character.name;
  setCharacterSearchStatus(`已定位：${character.name} / ${character.version}`, 'success');
}
function renderCharacterCatalog() {
  const grouped = characterCatalog.reduce((acc, character) => {
    const major = getMajorVersion(character.version);
    acc[major] ??= {};
    acc[major][character.version] ??= [];
    acc[major][character.version].push(character);
    return acc;
  }, {});

  versionTree.innerHTML = Object.keys(grouped)
    .sort(compareVersionLabel)
    .map((major) => {
      const minorHtml = Object.keys(grouped[major])
        .sort(compareVersionLabel)
        .map((minor) => `
          <details class="minor-version" open>
            <summary>${minor}</summary>
            <div class="character-list">
              ${grouped[major][minor]
                .map((character) => `
                  <button type="button" data-character-id="${character.id}" class="character-entry">
                    <span class="character-entry__avatar">
                      ${character.portrait ? `<img src="${character.portrait}" alt="${character.name}立绘缩略图">` : '<span></span>'}
                    </span>
                    <span class="character-entry__name">${character.name}</span>
                    <small>${character.version}</small>
                  </button>
                `)
                .join('')}
            </div>
          </details>
        `)
        .join('');

      return `
        <details class="major-version" open>
          <summary>${major} 大版本</summary>
          ${minorHtml}
        </details>
      `;
    })
    .join('');
}

function renderCharacterScores(scores = {}) {
  const items = [
    { key: 'character', label: '角色塑造', value: scores.character ?? 0 },
    { key: 'gameplay', label: '玩法体验', value: scores.gameplay ?? 0 },
    { key: 'systempain', label: '系统压力', value: scores.systempain ?? 0 },
  ];

  return '<div class="character-score-grid" aria-label="角色评分">' +
    items.map((item) =>
      '<div class="character-score-card" data-score-kind="' + item.key + '">' +
        '<span class="character-score-label">' + item.label + '</span>' +
        '<strong>' + item.value + '</strong>' +
      '</div>'
    ).join('') +
    '</div>';
}
function renderCharacterRisks(warnings = []) {
  if (!warnings.length) {
    return '<div class="character-risk-empty">暂无风险警告</div>';
  }

  return '<div class="character-risk-heading"><span>风险警告</span><strong>Risk Notice</strong></div>' +
    '<div class="character-risk-list">' +
    warnings.map((item, index) =>
      '<details class="character-risk-item"' + (index === 0 ? ' open' : '') + '>' +
        '<summary><span class="risk-level">' + item.level + '</span><span class="risk-title"> - ' + item.title + '</span></summary>' +
        '<p>' + item.description + '</p>' +
      '</details>'
    ).join('') +
    '</div>';
}
function renderCharacterKeywords(keywords = [], commentCount = 0) {
  const keywordBody = keywords.length
    ? '<div class="character-keyword-list">' +
      keywords.map((item) =>
        '<div class="character-keyword-item">' +
          '<span class="keyword-word">' + escapeHtml(item.keyword) + '</span>' +
          '<span class="keyword-weight">' + escapeHtml(item.weight) + '</span>' +
          '<span class="keyword-sentiment keyword-sentiment--' + escapeHtml(item.sentiment) + '">' + escapeHtml(item.sentiment) + '</span>' +
        '</div>'
      ).join('') +
      '</div>'
    : '<div class="character-keyword-empty">暂无关键词</div>';

  return '<div class="character-keyword-heading"><span>关键词</span><strong>Keyword Weight</strong></div>' +
    keywordBody +
    '<div class="character-comment-action">' +
      '<button type="button" class="ghost-button character-comment-button" data-character-comments>' +
        '查看相关评论' +
        '<span>' + commentCount + '</span>' +
      '</button>' +
    '</div>';
}
function renderCharacterStory(character = {}) {
  const rawStory = character.personalStory ?? character.personal_story ?? character.story ?? character.profileStory ?? '';
  const storyText = String(rawStory || '').trim();
  const body = storyText
    ? '<p>' + escapeHtml(storyText).replaceAll('\n', '<br>') + '</p>'
    : '<div class="character-story-empty">个人故事文本待补充</div>';

  return '<div class="character-story-heading"><span>个人故事</span><strong>Profile Story</strong></div>' +
    '<div class="character-story-body">' + body + '</div>';
}
async function selectCharacter(characterId, options = {}) {
  const character = characterCatalog.find((item) => String(item.id) === String(characterId));
  if (!character) return;

  currentCharacterId = String(character.id);

  selectedCharacterName.textContent = character.name;
  selectedCharacterMeta.textContent = `版本：${getMajorVersion(character.version)} 大版本 / ${character.version} 小版本`;

  const portraitMarkup = character.portrait
    ? `<img src="${character.portrait}" alt="${character.name}立绘">`
    : '<span>立绘待补充</span>';

  portraitPlaceholder.innerHTML = '<div class="portrait-stage">' + portraitMarkup + '</div>' + renderCharacterScores(character.scores);
  characterRiskPanel.innerHTML = renderCharacterRisks(character.riskWarnings);
  characterKeywordPanel.innerHTML = renderCharacterKeywords(character.characterKeywords, character.associatedCommentIds?.length ?? 0);
  if (characterStoryPanel) characterStoryPanel.innerHTML = renderCharacterStory(character);

  document.querySelectorAll('[data-character-id]').forEach((button) => {
    const isSelected = button.dataset.characterId === String(characterId);
    button.classList.toggle('is-selected', isSelected);
    if (isSelected) {
      button.closest('details')?.setAttribute('open', '');
      button.closest('.major-version')?.setAttribute('open', '');
    }
  });

  if (options.scrollToDetail) {
    document.querySelector('.character-detail')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  characterRiskPanel.innerHTML = '<div class="character-risk-empty">正在从 FastAPI 读取角色诊断，本地数据已先展示...</div>';

  await loadCharacterDiagnosisFromFastApi(character);
  if (currentCharacterId !== String(character.id)) return;

  portraitPlaceholder.innerHTML = '<div class="portrait-stage">' + portraitMarkup + '</div>' + renderCharacterScores(character.scores);
  characterRiskPanel.innerHTML = renderCharacterRisks(character.riskWarnings);
  characterKeywordPanel.innerHTML = renderCharacterKeywords(character.characterKeywords, character.associatedCommentIds?.length ?? 0);
  if (characterStoryPanel) characterStoryPanel.innerHTML = renderCharacterStory(character);
}
function showModuleView(viewId) {
  moduleViews.forEach((view) => {
    view.classList.toggle('module-view--active', view.id === viewId);
  });

  viewButtons.forEach((button) => {
    button.classList.toggle('is-active', button.dataset.viewTarget === viewId);
  });
}

function showPage(pageId) {
  pageScreens.forEach((page) => {
    page.classList.toggle('page-screen--active', page.id === pageId);
  });

  pageButtons.forEach((button) => {
    button.classList.toggle('is-current', button.dataset.pageTarget === pageId);
  });
}

function findNextViolationId(preferredIndex = 0) {
  const fromCurrent = scriptLines.slice(preferredIndex).find((line) => line.violationId)?.violationId;
  return fromCurrent ?? scriptLines.find((line) => line.violationId)?.violationId ?? null;
}

function rescanScriptAfterReplacement(fromIndex = 0) {
  renderScript();
  updateRedlineStats();
  const nextViolation = findNextViolationId(fromIndex);
  renderSuggestions(nextViolation);
  scriptEditor.classList.add('script-editor--rescanned');
  window.setTimeout(() => scriptEditor.classList.remove('script-editor--rescanned'), 560);
}


function renderScript() {
  if (!scriptEditor) return;
  scriptEditor.innerHTML = scriptLines
    .map((line, index) => {
      const text = escapeHtml(line.text);
      const textClass = line.violationId ? 'script-line-text bad-line' : 'script-line-text';
      const violationAttr = line.violationId ? ` data-violation-id="${line.violationId}"` : '';

      return `
        <p data-line-index="${index}">
          <span class="line-number">${index + 1}</span>
          <span class="${textClass}" data-line-index="${index}"${violationAttr} contenteditable="true" spellcheck="false">${text}</span>
        </p>
      `;
    })
    .join('');
}

function syncEditedScriptLine(target) {
  const editableLine = target.closest('[data-line-index].script-line-text');
  if (!editableLine) return;

  const lineIndex = Number(editableLine.dataset.lineIndex);
  if (!Number.isInteger(lineIndex) || !scriptLines[lineIndex]) return;

  scriptLines[lineIndex] = {
    text: editableLine.textContent.trim(),
    violationId: null,
  };
}

function focusScriptLine(lineIndex) {
  const target = scriptEditor.querySelector(`.script-line-text[data-line-index="${lineIndex}"]`);
  if (!target) return;

  target.focus();
  const range = document.createRange();
  range.selectNodeContents(target);
  range.collapse(false);

  const selection = window.getSelection();
  selection.removeAllRanges();
  selection.addRange(range);
}

function insertScriptLineAfter(target) {
  const editableLine = target.closest('[data-line-index].script-line-text');
  if (!editableLine) return;

  syncEditedScriptLine(editableLine);
  const lineIndex = Number(editableLine.dataset.lineIndex);
  if (!Number.isInteger(lineIndex)) return;

  scriptLines.splice(lineIndex + 1, 0, { text: '', violationId: null });
  renderScript();
  updateRedlineStats();
  focusScriptLine(lineIndex + 1);
}

function removeEmptyScriptLine(target) {
  const editableLine = target.closest('[data-line-index].script-line-text');
  if (!editableLine) return false;

  const lineIndex = Number(editableLine.dataset.lineIndex);
  if (!Number.isInteger(lineIndex) || scriptLines.length <= 1) return false;
  if (editableLine.textContent.trim().length > 0) return false;

  scriptLines.splice(lineIndex, 1);
  renderScript();
  updateRedlineStats();
  focusScriptLine(Math.max(0, lineIndex - 1));
  return true;
}function detectViolationForLine(text) {
  const normalizedText = text.trim();
  if (!normalizedText) return null;

  if (/角落|沉默|旁观|等待.*解释|背景板/.test(normalizedText)) return 'v1';
  if (/听我的安排|只要听|替.*决定|归功于.*指挥/.test(normalizedText)) return 'v2';
  if (/没有获得表达|没有.*机会|失去表达|迟疑.*没有/.test(normalizedText)) return 'v3';

  return null;
}

function runScriptCheck() {
  scriptLines.forEach((line) => {
    line.violationId = detectViolationForLine(line.text);
  });
  rescanScriptAfterReplacement(0);
}

function renderSuggestions(violationId) {
  if (!suggestionList) return;
  const violation = violations[violationId];
  if (!violation) {
    activeViolationId = null;
    suggestionList.innerHTML = '<p class="empty-state">当前没有待修改段落，红线复扫完成。</p>';
    document.querySelectorAll('.bad-line').forEach((node) => node.classList.remove('bad-line--active'));
    return;
  }

  activeViolationId = violationId;
  suggestionList.innerHTML = violation.suggestions
    .map((suggestion, index) => `
      <article class="suggestion-card">
        <div class="suggestion-card__header">
          <span>改写版本 ${index + 1}</span>
          <strong>${violation.severity}</strong>
        </div>
        <p>${suggestion}</p>
        <button type="button" data-apply="${index}" data-apply-violation="${violationId}">采用修改</button>
      </article>
    `)
    .join('');

  document.querySelectorAll('.bad-line').forEach((node) => {
    node.classList.toggle('bad-line--active', node.dataset.violationId === violationId);
  });
}

function updateRedlineStats() {
  const totalChars = scriptLines.reduce((sum, line) => sum + line.text.length, 0);
  const violationLines = scriptLines.filter((line) => line.violationId);
  const violationChars = violationLines.reduce((sum, line) => sum + line.text.length, 0);
  const ratio = totalChars ? Math.round((violationChars / totalChars) * 100) : 0;

  violationCount.textContent = String(violationLines.length);
  totalCharCount.textContent = String(totalChars);
  violationRatio.textContent = `${ratio}%`;
  ratioMeterFill.style.width = `${ratio}%`;
}

function renderCommentList(comments = []) {
  if (!comments.length) {
    return '<article class="source-item source-item--empty"><p>暂无可追溯评论。</p></article>';
  }

  return comments.map((comment) => {
    const url = comment.url ? escapeHtml(comment.url) : '';
    const link = url
      ? '<a class="source-link" href="' + url + '" target="_blank" rel="noreferrer">跳转链接</a>'
      : '<span class="source-link source-link--disabled">暂无链接</span>';

    return '<article class="source-item source-item--comment">' +
      '<div class="source-item__meta">' +
        '<span>' + escapeHtml(comment.platform || '未知平台') + '</span>' +
        '<small>#' + escapeHtml(comment.id) + '</small>' +
      '</div>' +
      '<p>' + escapeHtml(comment.content || '暂无内容') + '</p>' +
      '<div class="source-item__footer">' + link + '</div>' +
    '</article>';
  }).join('');
}

async function openCharacterComments(characterId) {
  const character = characterCatalog.find((item) => String(item.id) === String(characterId));
  if (!character) return;

  dialogTitle.textContent = `${character.name} 相关评论`;
  sourceList.innerHTML = '<article class="source-item source-item--empty"><p>正在读取评论...</p></article>';
  sourceOverlay.hidden = false;

  const ids = character.associatedCommentIds ?? [];
  if (!ids.length) {
    sourceList.innerHTML = renderCommentList([]);
    return;
  }

  try {
    const payload = await fetchFastApi('/api/comments/trace?ids=' + encodeURIComponent(ids.join(',')));
    sourceList.innerHTML = renderCommentList(normalizeCommentItems(payload));
  } catch (error) {
    console.warn('Failed to load related comments:', error);
    sourceList.innerHTML = '<article class="source-item source-item--empty"><p>评论读取失败，请确认 FastAPI 后端已在 8000 端口启动。</p></article>';
  }
}


function showFloatingToast(message = '下载成功') {
  let toast = document.querySelector('#floatingToast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'floatingToast';
    toast.className = 'floating-toast';
    document.body.appendChild(toast);
  }
  toast.textContent = message;
  toast.classList.add('is-visible');
  window.clearTimeout(showFloatingToast.timer);
  showFloatingToast.timer = window.setTimeout(() => {
    toast.classList.remove('is-visible');
  }, 3000);
}

async function saveReportToUserLocation(fileName, content, mimeType = 'text/markdown;charset=utf-8') {
  const blob = new Blob(['\ufeff', content], { type: mimeType });
  if ('showDirectoryPicker' in window) {
    const directoryHandle = await window.showDirectoryPicker({ mode: 'readwrite' });
    const fileHandle = await directoryHandle.getFileHandle(fileName, { create: true });
    const writable = await fileHandle.createWritable();
    await writable.write(blob);
    await writable.close();
    return;
  }
  if ('showSaveFilePicker' in window) {
    const fileHandle = await window.showSaveFilePicker({
      suggestedName: fileName,
      types: [{ description: 'Markdown report', accept: { 'text/markdown': ['.md'] } }],
    });
    const writable = await fileHandle.createWritable();
    await writable.write(blob);
    await writable.close();
    return;
  }
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
function showTooltip(event, violationId) {
  if (!tooltip) return;
  const violation = violations[violationId];
  if (!violation) return;
  tooltip.textContent = violation.reason;
  tooltip.style.left = `${event.clientX + 16}px`;
  tooltip.style.top = `${event.clientY + 16}px`;
  tooltip.classList.add('tooltip--visible');
}

function hideTooltip() {
  if (!tooltip) return;
  tooltip.classList.remove('tooltip--visible');
}


async function exportReport() {
  const characterId = currentCharacterId ? `character_id=${encodeURIComponent(currentCharacterId)}&` : '';
  const path = `/api/report/export?${characterId}days=30`;

  if (exportReportButton) {
    exportReportButton.disabled = true;
    exportReportButton.textContent = '正在生成';
  }

  try {
    const payload = await fetchFastApi(path, { timeoutMs: 20000, modal: true });
    if (!payload?.success || !payload.content) throw new Error(payload?.error || 'report payload empty');
    if (exportReportButton) exportReportButton.textContent = '选择目录';
    await saveReportToUserLocation(payload.file_name || 'GamePulse_舆情报告.md', payload.content, payload.mime_type);
    hideNetworkNotice();
    showFloatingToast('下载成功');
  } catch (error) {
    if (error?.name === 'AbortError') {
      console.info('Report export cancelled by user.');
      return;
    }
    console.warn('Failed to export report:', error);
    const message = error?.name === 'NotAllowedError'
      ? '下载已取消：未选择保存目录。'
      : '报告导出失败：请确认后端服务和数据库可用。';
    showNetworkNotice(message, path, { modal: true });
  } finally {
    if (exportReportButton) {
      exportReportButton.disabled = false;
      exportReportButton.textContent = '导出报告';
    }
  }
}
exportReportButton?.addEventListener('click', exportReport);

retryNetworkButton?.addEventListener('click', async () => {
  hideNetworkNotice();
  try {
    await fetchFastApi(lastFailedApiPath || '/health', { modal: true });
  } catch (error) {
    console.warn('Retry failed:', error);
  }
});

dismissNetworkButton?.addEventListener('click', hideNetworkNotice);

assistantForm?.addEventListener('submit', (event) => {
  event.preventDefault();
  sendAssistantMessage(assistantInput?.value ?? '');
});

document.querySelectorAll('[data-assistant-prompt]').forEach((button) => {
  button.addEventListener('click', () => {
    showPage('assistantPage');
    sendAssistantMessage(button.dataset.assistantPrompt ?? '');
  });
});

document.addEventListener('click', (event) => {
  const characterButton = event.target.closest('[data-character-id]');
  if (characterButton) {
    void selectCharacter(characterButton.dataset.characterId).then(() => {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
    return;
  }


  const commentButton = event.target.closest('[data-character-comments]');
  if (commentButton) {
    openCharacterComments(currentCharacterId);
    return;
  }

  const badLine = event.target.closest('.bad-line');
  if (badLine) {
    renderSuggestions(badLine.dataset.violationId);
    return;
  }

  const applyButton = event.target.closest('[data-apply]');
  if (applyButton) {
    const targetViolationId = applyButton.dataset.applyViolation || activeViolationId;
    const replacement = violations[targetViolationId]?.suggestions[Number(applyButton.dataset.apply)];
    const lineIndex = scriptLines.findIndex((line) => line.violationId === targetViolationId);
    if (lineIndex >= 0 && replacement) {
      scriptLines[lineIndex] = { text: replacement, violationId: null };
      applyButton.textContent = '已采用，正在复扫';
      applyButton.disabled = true;
      rescanScriptAfterReplacement(lineIndex);
    }
    return;
  }
});

scriptEditor?.addEventListener('input', (event) => {
  syncEditedScriptLine(event.target);
  updateRedlineStats();
});

scriptEditor?.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') {
    event.preventDefault();
    insertScriptLineAfter(event.target);
    return;
  }

  if ((event.key === 'Backspace' || event.key === 'Delete') && removeEmptyScriptLine(event.target)) {
    event.preventDefault();
  }
});

scriptEditor?.addEventListener('mousemove', (event) => {
  const badLine = event.target.closest('.bad-line');
  if (!badLine) {
    hideTooltip();
    return;
  }

  showTooltip(event, badLine.dataset.violationId);
});

scriptEditor?.addEventListener('mouseleave', hideTooltip);

closeDialogButton?.addEventListener('click', () => {
  sourceOverlay.hidden = true;
});

sourceOverlay?.addEventListener('click', (event) => {
  if (event.target === sourceOverlay) {
    sourceOverlay.hidden = true;
  }
});

viewButtons.forEach((button) => {
  button.addEventListener('click', () => showModuleView(button.dataset.viewTarget));
});

pageButtons.forEach((button) => {
  button.addEventListener('click', () => {
    showPage(button.dataset.pageTarget);
  });
});


const agentFlowLabels = [
  '接收用户输入并建立任务上下文',
  '识别问题类型与目标模块',
  '读取角色、评论和风险卡上下文',
  '推理风险级别与可解释依据',
  '组织回答并回写对话窗口',
];
let agentFlowTimer = null;

function setAgentFlowStep(index, label = null) {
  if (!agentFlowSteps.length) return;
  agentFlowSteps.forEach((step, stepIndex) => {
    step.classList.toggle('is-active', stepIndex === index);
    step.classList.toggle('is-complete', stepIndex < index);
  });
  if (agentFlowStatus) agentFlowStatus.textContent = label ?? agentFlowLabels[index] ?? '流程待命';
}

function runAgentFlow() {
  if (!agentFlowSteps.length) return;
  window.clearInterval(agentFlowTimer);
  agentFlow?.classList.add('is-running');
  setAgentFlowStep(0, agentFlowLabels[0]);
  let index = 0;
  agentFlowTimer = window.setInterval(() => {
    index += 1;
    if (index >= agentFlowLabels.length) {
      window.clearInterval(agentFlowTimer);
      setAgentFlowStep(agentFlowLabels.length - 1, '回复已生成，等待下一次输入');
      window.setTimeout(() => agentFlow?.classList.remove('is-running'), 650);
      return;
    }
    setAgentFlowStep(index, agentFlowLabels[index]);
  }, 360);
}
function sanitizeAssistantText(text = '') {
  return String(text || '')
    .split('\n')
    .map((rawLine) => {
      let line = rawLine.trim();
      if (!line || ['---', '***', '___'].includes(line)) return '';
      line = line.replace(/^#{1,6}\s*/, '');
      line = line.replace(/^[-*+]\s+/, '');
      line = line.replaceAll('**', '').replaceAll('__', '').replaceAll('`', '');
      line = line.replace(/[\u{1F300}-\u{1FAFF}\u2600-\u27BF]/gu, '');
      if (/^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$/.test(line)) return '';
      if (line.includes('|') && (line.match(/\|/g) || []).length >= 2) {
        const cells = line.split('|').map((cell) => cell.trim()).filter(Boolean);
        if (cells.length) line = cells.join('；');
      }
      return line;
    })
    .filter(Boolean)
    .join('\n')
    .trim();
}
function appendAssistantMessage(role, text, meta = null) {
  if (!assistantMessages) return null;

  const article = document.createElement('article');
  article.className = `assistant-message assistant-message--${role}`;
  const displayText = role === 'ai' ? sanitizeAssistantText(text) : String(text || '');
  const body = escapeHtml(displayText).replaceAll('\n', '<br>');
  const metaHtml = meta ? `<div class="assistant-calltrace">${escapeHtml(meta)}</div>` : '';
  article.innerHTML = `
    <div class="assistant-avatar">${role === 'user' ? 'ME' : 'AI'}</div>
    <div class="assistant-bubble"><p>${body}</p>${metaHtml}</div>
  `;
  assistantMessages.appendChild(article);
  assistantMessages.scrollTop = assistantMessages.scrollHeight;
  return article;
}

function updateAssistantMessage(article, text, meta = null) {
  if (!article) return;
  const bubble = article.querySelector('.assistant-bubble');
  if (!bubble) return;
  const body = escapeHtml(sanitizeAssistantText(text)).replaceAll('\n', '<br>');
  const metaHtml = meta ? `<div class="assistant-calltrace">${escapeHtml(meta)}</div>` : '';
  bubble.innerHTML = `<p>${body}</p>${metaHtml}`;
  assistantMessages.scrollTop = assistantMessages.scrollHeight;
}

function formatAssistantTrace(payload = {}) {
  const agents = payload.called_agents ?? [];
  const tools = payload.called_tools ?? [];
  const parts = [];
  if (agents.length) parts.push(`agents: ${agents.join(' → ')}`);
  if (tools.length) parts.push(`tools: ${tools.join(' → ')}`);
  if (!parts.length) parts.push('tools: none');
  return parts.join('  |  ');
}

function formatRuntimeEvent(event = {}) {
  const name = event.name || 'unknown';
  const detail = event.detail ? `：${event.detail}` : '';
  const labels = {
    status: '准备',
    agent_start: '进入 Agent',
    agent_end: '完成 Agent',
    tool_start: '调用 Tool',
    tool_end: 'Tool 返回',
    tool_error: 'Tool 失败',
  };
  return `${labels[event.type] || event.type} · ${name}${detail}`;
}

function renderRuntimeEvents(events = []) {
  if (!events.length) return '正在等待总控 Agent 选择调用路径...';
  return events.map((event, index) => `${index + 1}. ${formatRuntimeEvent(event)}`).join('\n');
}

function updateAgentFlowFromEvent(event = {}) {
  if (!agentFlowSteps.length) return;
  agentFlow?.classList.add('is-running');
  const type = event.type;
  let index = 0;
  if (type === 'agent_start' && event.name === 'orchestrator') index = 1;
  else if (type === 'tool_start') index = 2;
  else if (type === 'tool_end' || type === 'tool_error') index = 3;
  else if (type === 'agent_end') index = 4;
  setAgentFlowStep(index, formatRuntimeEvent(event));
}

async function getAssistantSessionId() {
  if (assistantSessionId) return assistantSessionId;
  const payload = await fetchFastApi('/sessions', {
    timeoutMs: 8000,
    fetchOptions: {
      method: 'POST',
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
      body: JSON.stringify({
        character_id: Number(currentCharacterId) || 0,
        title: '前端助手会话',
        current_text: '',
        selected_constraints: [],
        custom_constraint: null,
      }),
    },
    modal: true,
  });
  assistantSessionId = payload.session_id;
  return assistantSessionId;
}

async function sendAssistantMessage(text) {
  const question = text.trim();
  if (!question || assistantBusy) return;

  assistantBusy = true;
  appendAssistantMessage('user', question);
  appendOperationLog('REQUEST', `用户输入：${question.slice(0, 140)}`, 'request');
  if (assistantInput) {
    assistantInput.value = '';
    assistantInput.disabled = true;
  }
  const runtimeEvents = [];
  const pendingMessage = appendAssistantMessage('ai', '正在调用 GamePulse 总控 Agent...');
  setAgentFlowStep(0, '已收到输入，正在建立任务上下文');
  agentFlow?.classList.add('is-running');

  try {
    appendOperationLog('SESSION', assistantSessionId ? `复用会话：${assistantSessionId}` : '请求创建新会话', 'request');
    const sessionId = await getAssistantSessionId();
    appendOperationLog('SESSION', `会话已就绪：${sessionId}`, 'response');

    const requestStartedAt = performance.now();
    appendOperationLog('HTTP', `POST ${FASTAPI_BASE_URL}/chat/stream`, 'request');
    const response = await fetch(`${FASTAPI_BASE_URL}/chat/stream`, {
      method: 'POST',
      cache: 'no-store',
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
      body: JSON.stringify({
        session_id: sessionId,
        message: question,
        shared_context: {
          selected_character_id: currentCharacterId,
          selected_character_name: selectedCharacterName?.textContent?.trim() || '',
        },
      }),
    });
    const elapsedMs = Math.round(performance.now() - requestStartedAt);
    appendOperationLog('HTTP', `响应 ${response.status} ${response.statusText || ''}；${elapsedMs}ms`, response.ok ? 'response' : 'error');
    if (!response.ok || !response.body) throw new Error(`FastAPI ${response.status}: /chat/stream`);

    hideNetworkNotice();
    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';
    let finalPayload = null;

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      for (const line of lines) {
        if (!line.trim()) continue;
        const event = JSON.parse(line);
        if (event.type === 'final') {
          finalPayload = event.payload || {};
          continue;
        }
        runtimeEvents.push(event);
        logRuntimeEvent(event);
        updateAgentFlowFromEvent(event);
        updateAssistantMessage(pendingMessage, renderRuntimeEvents(runtimeEvents), '实时调用链路更新中');
      }
    }

    if (buffer.trim()) {
      const event = JSON.parse(buffer);
      if (event.type === 'final') finalPayload = event.payload || {};
      else logRuntimeEvent(event);
    }

    if (!finalPayload) throw new Error('stream finished without final payload');
    setAgentFlowStep(4, '回复已生成，等待下一次输入');
    window.setTimeout(() => agentFlow?.classList.remove('is-running'), 650);
    appendOperationLog('FINAL', summarizeFinalPayload(finalPayload), finalPayload.success === false ? 'error' : 'response');
    updateAssistantMessage(pendingMessage, finalPayload.answer || '总控 Agent 没有返回内容。', formatAssistantTrace(finalPayload));
  } catch (error) {
    console.warn('GamePulse assistant request failed:', error);
    appendOperationLog('ERROR', error?.message || String(error), 'error');
    showNetworkNotice('GamePulse 助手调用失败，请确认后端服务和模型 API 可用。', '/chat/stream', { modal: false });
    setAgentFlowStep(4, '调用失败，请检查后端或模型 API');
    updateAssistantMessage(pendingMessage, 'GamePulse 后端暂时不可用，请确认 FastAPI 服务已启动并配置模型 API Key。', 'tools: request_failed');
  } finally {
    assistantBusy = false;
    if (assistantInput) {
      assistantInput.disabled = false;
      assistantInput.focus();
    }
  }
}
async function loadInitialFastApiState() {
  try {
    await fetchFastApi('/health');
    return true;
  } catch (error) {
    console.warn('FastAPI backend is not reachable yet, using built-in fallback data:', error);
    return false;
  }
}

async function initApp() {
  loadInitialFastApiState();
  loadDatabaseSummary();
  renderCharacterCatalog();
  renderCharacterSearchOptions();
  selectCharacter(characterCatalog.find((character) => character.portrait)?.id ?? characterCatalog[0]?.id);
  showPage('resonatorPage');
}
characterSearchForm?.addEventListener('submit', (event) => {
  event.preventDefault();
  jumpToCharacterByName(characterSearchInput?.value ?? '');
});

characterSearchInput?.addEventListener('input', () => {
  const value = characterSearchInput.value.trim();
  if (!value) {
    setCharacterSearchStatus('输入角色名后按 Enter 定位角色。');
    return;
  }

  const character = findCharacterBySearch(value);
  setCharacterSearchStatus(character ? `候选：${character.name} / ${character.version}` : '暂无匹配角色', character ? 'success' : 'error');
});

if (customCursor && window.matchMedia('(pointer: fine)').matches) {
  document.addEventListener('mousemove', (event) => {
    customCursor.style.left = `${event.clientX}px`;
    customCursor.style.top = `${event.clientY}px`;
  });

  document.addEventListener('mousedown', () => customCursor.classList.add('active'));
  document.addEventListener('mouseup', () => customCursor.classList.remove('active'));

  document.addEventListener('mouseover', (event) => {
    const interactive = event.target.closest('button, .bad-line, a, details, summary, .network-panel, .assistant-chat');
    customCursor.classList.toggle('hovering', Boolean(interactive));
    customCursor.classList.toggle('problem', Boolean(event.target.closest('.bad-line')));
  });
}

initApp();



































