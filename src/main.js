/* ============================================================
   SPARK — Scholarly Publication & Academic Ranking Knowledgebase
   Main Application Logic
   ============================================================ */

import './index.css';

// ── State ──────────────────────────────────────────────────
let data = null;
let filters = {
  rankFilter: 'all', // 'all', 'astar', 'a'
  areaFilter: 'all',
  searchQuery: '',
  activeTab: 'rankings',
};
let expandedInstitution = null;

// ── Routing ────────────────────────────────────────────────
function getCurrentRoute() {
  const hash = window.location.hash || '';
  // Match: #/faculty/{instShort}/{dblpPid}
  const facultyMatch = hash.match(/^#\/faculty\/([^/]+)\/(.+)$/);
  if (facultyMatch) {
    return { page: 'faculty', instShort: decodeURIComponent(facultyMatch[1]), dblpPid: decodeURIComponent(facultyMatch[2]) };
  }
  return { page: 'home' };
}

function navigateTo(hash) {
  window.location.hash = hash;
}

function goHome() {
  window.location.hash = '';
}

// ── Data Loading ───────────────────────────────────────────
async function loadData() {
  try {
    const resp = await fetch('/data/rankings.json');
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    data = await resp.json();
    return true;
  } catch (err) {
    console.error('Failed to load ranking data:', err);
    return false;
  }
}

// ── Utility Functions ──────────────────────────────────────
function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function safeId(str) {
  return str.replace(/[^a-zA-Z0-9_-]/g, '-');
}

function formatScore(score) {
  return score.toFixed(1);
}

function getUniqueAreas(institutions) {
  const areas = new Set();
  for (const inst of institutions) {
    for (const area of inst.area_breakdown || []) {
      areas.add(JSON.stringify({ code: area.for_code, desc: area.description }));
    }
  }
  return [...areas].map(a => JSON.parse(a)).sort((a, b) => a.desc.localeCompare(b.desc));
}

function getMaxScore(institutions) {
  return Math.max(...institutions.map(i => i.total_score), 1);
}

function getFilteredPubs(faculty) {
  let pubs = faculty.publications || [];
  if (filters.rankFilter === 'astar') {
    pubs = pubs.filter(p => p.venue_rank === 'A*');
  } else if (filters.rankFilter === 'a') {
    pubs = pubs.filter(p => p.venue_rank === 'A');
  }
  if (filters.areaFilter !== 'all') {
    pubs = pubs.filter(p => p.for_code === filters.areaFilter);
  }
  return pubs;
}

function getFilteredScore(faculty) {
  return getFilteredPubs(faculty).reduce((sum, p) => sum + p.adjusted_count, 0);
}

function getFilteredInstitutionScore(inst) {
  return (inst.faculty || []).reduce((sum, f) => sum + getFilteredScore(f), 0);
}

function getFilteredPaperCounts(faculty) {
  const pubs = getFilteredPubs(faculty);
  return {
    astar: pubs.filter(p => p.venue_rank === 'A*').length,
    a: pubs.filter(p => p.venue_rank === 'A').length,
    total: pubs.length,
  };
}

function matchesSearch(text) {
  if (!filters.searchQuery) return true;
  return text.toLowerCase().includes(filters.searchQuery.toLowerCase());
}

// Count publications per conference across all institutions
function getConferencePubCounts() {
  const counts = {};
  for (const inst of data.institutions) {
    for (const fac of inst.faculty) {
      for (const pub of fac.publications) {
        const key = pub.venue;
        if (!counts[key]) counts[key] = 0;
        counts[key]++;
      }
    }
  }
  return counts;
}

// ── Render Functions ───────────────────────────────────────
function render() {
  const app = document.getElementById('app');

  // Hide loading
  const loading = document.getElementById('loading-screen');
  if (loading) loading.classList.add('hidden');

  if (!data) {
    app.innerHTML = renderNoData();
    return;
  }

  const route = getCurrentRoute();

  if (route.page === 'faculty') {
    renderFacultyDetailPage(app, route.instShort, route.dblpPid);
    return;
  }

  app.innerHTML = `
    <div class="bg-grid"></div>
    <div class="bg-glow bg-glow-1"></div>
    <div class="bg-glow bg-glow-2"></div>

    ${renderHero()}

    <div class="container">
      ${renderTabs()}
      <div id="tab-rankings" class="tab-content ${filters.activeTab === 'rankings' ? 'active' : ''}">
        ${renderControls()}
        ${renderRankingSection()}
      </div>
      <div id="tab-areas" class="tab-content ${filters.activeTab === 'areas' ? 'active' : ''}">
        ${renderAreaBreakdown()}
      </div>
      <div id="tab-conferences" class="tab-content ${filters.activeTab === 'conferences' ? 'active' : ''}">
        ${renderConferenceExplorer()}
      </div>
      <div id="tab-methodology" class="tab-content ${filters.activeTab === 'methodology' ? 'active' : ''}">
        ${renderMethodology()}
      </div>

      ${renderFooter()}
    </div>
  `;

  attachEventListeners();
}

function renderNoData() {
  return `
    <div class="bg-grid"></div>
    <div class="container">
      <div class="no-data" style="margin-top: 20vh;">
        <div class="no-data-icon">📊</div>
        <h2 style="margin-bottom: 1rem; font-size: 1.5rem;">No Ranking Data Found</h2>
        <p>Please run the data pipeline first to generate <code>data/rankings.json</code></p>
        <p style="margin-top: 1rem; font-size: 0.8rem; color: var(--text-muted);">
          1. <code>python pipeline/scrape_icore.py</code><br>
          2. <code>python pipeline/fetch_publications.py</code>
        </p>
      </div>
    </div>
  `;
}

function renderHero() {
  const yearRange = data.year_range || [2015, 2025];
  const totalPapers = data.institutions.reduce((s, i) => s + i.total_papers, 0);
  const totalFaculty = data.institutions.reduce((s, i) => s + i.faculty_count, 0);

  return `
    <header class="hero">
      <div class="container">
        <div class="hero-badge animate-in">
          <span class="dot"></span>
          ICORE ${data.conference_source || '2026'} • Live Data
        </div>
        <h1 class="animate-in">
          <span class="gradient-text">SPARK</span>
        </h1>
        <p class="hero-description animate-in">
          Scholarly Publication & Academic Ranking Knowledgebase — ranking CS departments using
          <strong>all ${data.total_conferences_tracked || 170} ICORE A*/A conferences</strong>,
          not just the CSRankings subset.
        </p>

        <div class="stats-bar animate-in">
          <div class="stat-item">
            <div class="stat-value gold">${data.total_conferences_astar || 0}</div>
            <div class="stat-label">A* Conferences</div>
          </div>
          <div class="stat-item">
            <div class="stat-value">${data.total_conferences_a || 0}</div>
            <div class="stat-label">A Conferences</div>
          </div>
          <div class="stat-item">
            <div class="stat-value emerald">${totalPapers}</div>
            <div class="stat-label">Papers Matched</div>
          </div>
          <div class="stat-item">
            <div class="stat-value">${totalFaculty}</div>
            <div class="stat-label">Faculty Tracked</div>
          </div>
          <div class="stat-item">
            <div class="stat-value">${yearRange[0]}–${yearRange[1]}</div>
            <div class="stat-label">Year Range</div>
          </div>
        </div>
      </div>
    </header>
  `;
}

function renderTabs() {
  const tabs = [
    { id: 'rankings', label: '🏆 Rankings', },
    { id: 'areas', label: '📊 Areas', },
    { id: 'conferences', label: '📚 Conferences', },
    { id: 'methodology', label: '📋 Methodology', },
  ];
  return `
    <div class="tabs">
      ${tabs.map(t => `
        <button class="tab-btn ${filters.activeTab === t.id ? 'active' : ''}"
                data-tab="${t.id}" id="tab-btn-${t.id}">
          ${t.label}
        </button>
      `).join('')}
    </div>
  `;
}

function renderControls() {
  const areas = getUniqueAreas(data.institutions);

  return `
    <div class="controls animate-in">
      <span class="controls-label">Rank</span>
      <div class="toggle-group">
        <button class="toggle-btn ${filters.rankFilter === 'all' ? 'active' : ''}"
                data-rank="all" id="rank-all">A* + A</button>
        <button class="toggle-btn ${filters.rankFilter === 'astar' ? 'active gold-active' : ''}"
                data-rank="astar" id="rank-astar">A* Only</button>
        <button class="toggle-btn ${filters.rankFilter === 'a' ? 'active' : ''}"
                data-rank="a" id="rank-a">A Only</button>
      </div>

      <span class="controls-label">Area</span>
      <div class="select-wrapper">
        <select class="select-input" id="area-filter">
          <option value="all">All Areas</option>
          ${areas.map(a => `
            <option value="${escapeHtml(a.code)}" ${filters.areaFilter === a.code ? 'selected' : ''}>
              ${escapeHtml(a.desc)}
            </option>
          `).join('')}
        </select>
      </div>

      <div class="search-wrapper">
        <span class="search-icon">🔍</span>
        <input type="text" class="search-input" id="search-input"
               placeholder="Search faculty or institution..."
               value="${escapeHtml(filters.searchQuery)}" />
      </div>
    </div>
  `;
}

function renderRankingSection() {
  const institutions = data.institutions
    .map(inst => ({
      ...inst,
      filteredScore: getFilteredInstitutionScore(inst),
      filteredFaculty: inst.faculty.filter(f => {
        const pubs = getFilteredPubs(f);
        return pubs.length > 0 && matchesSearch(f.name + ' ' + inst.name + ' ' + inst.short);
      }),
    }))
    .filter(inst => inst.filteredFaculty.length > 0 || matchesSearch(inst.name + ' ' + inst.short))
    .sort((a, b) => b.filteredScore - a.filteredScore);

  if (institutions.length === 0) {
    return `
      <div class="no-data">
        <div class="no-data-icon">🔍</div>
        <p>No matching results found.</p>
      </div>
    `;
  }

  const maxScore = Math.max(...institutions.map(i => i.filteredScore), 1);

  return `
    <section class="section" id="ranking-section">
      <div class="section-header">
        <span class="section-icon">🏆</span>
        <h2 class="section-title">Institution Rankings</h2>
        <span class="section-subtitle">${institutions.length} institution${institutions.length > 1 ? 's' : ''}</span>
      </div>
      <table class="ranking-table">
        <tbody>
          ${institutions.map((inst, idx) => renderInstitutionRow(inst, idx + 1, maxScore)).join('')}
        </tbody>
      </table>
    </section>
  `;
}

function renderInstitutionRow(inst, rank, maxScore) {
  const isExpanded = expandedInstitution === inst.short;
  const scorePercent = (inst.filteredScore / maxScore) * 100;

  // Get filtered paper counts for institution
  let totalAstar = 0;
  let totalA = 0;
  for (const f of inst.faculty) {
    const counts = getFilteredPaperCounts(f);
    totalAstar += counts.astar;
    totalA += counts.a;
  }

  const rankClass = rank <= 3 ? `rank-${rank}` : 'rank-n';

  return `
    <tr class="inst-row ${isExpanded ? 'expanded' : ''} animate-in"
        data-inst="${escapeHtml(inst.short)}" id="inst-row-${escapeHtml(inst.short)}">
      <td style="width: 50px;">
        <div class="rank-badge ${rankClass}">${rank}</div>
      </td>
      <td>
        <div class="inst-name">
          ${escapeHtml(inst.name)}
          <span class="inst-short">${escapeHtml(inst.short)}</span>
        </div>
        <span class="inst-country">${escapeHtml(inst.country)} · ${inst.faculty_count} faculty</span>
      </td>
      <td>
        <div class="paper-counts-cell">
          <span class="paper-count astar">★ ${totalAstar} A*</span>
          <span class="paper-count a-rank">● ${totalA} A</span>
        </div>
      </td>
      <td class="score-cell">
        <div class="score-value">${formatScore(inst.filteredScore)}</div>
        <div class="score-bar-wrapper">
          <div class="score-bar" style="width: ${scorePercent}%"></div>
        </div>
      </td>
      <td style="width: 30px;">
        <span class="expand-arrow">▶</span>
      </td>
    </tr>
    <tr class="faculty-panel ${isExpanded ? 'visible' : ''}" id="panel-${escapeHtml(inst.short)}">
      <td colspan="5">
        ${isExpanded ? renderFacultyPanel(inst) : ''}
      </td>
    </tr>
  `;
}

function renderFacultyPanel(inst) {
  const sortedFaculty = [...inst.faculty]
    .map(f => ({
      ...f,
      filteredScore: getFilteredScore(f),
      filteredCounts: getFilteredPaperCounts(f),
    }))
    .filter(f => f.filteredCounts.total > 0)
    .sort((a, b) => b.filteredScore - a.filteredScore);

  if (sortedFaculty.length === 0) {
    return `
      <div class="faculty-content">
        <div class="no-data" style="padding: 2rem;">
          <p>No matching publications for current filters.</p>
        </div>
      </div>
    `;
  }

  return `
    <div class="faculty-content">
      <div class="faculty-grid">
        ${sortedFaculty.map(f => renderFacultyCard(f, inst.short)).join('')}
      </div>
    </div>
  `;
}

function renderFacultyCard(faculty, instShort) {
  const counts = getFilteredPaperCounts(faculty);
  const score = getFilteredScore(faculty);
  const facultyHash = `#/faculty/${encodeURIComponent(instShort)}/${encodeURIComponent(faculty.dblp_pid)}`;

  return `
    <a class="faculty-card" href="${facultyHash}"
         id="faculty-${safeId(instShort + '_' + faculty.dblp_pid)}">
      <div class="faculty-card-header">
        <div>
          <div class="faculty-name">${escapeHtml(faculty.name)}</div>
          <div class="faculty-role">${escapeHtml(faculty.role)}</div>
        </div>
        <div class="faculty-score">${formatScore(score)}</div>
      </div>
      <div class="faculty-stats">
        <span class="paper-count astar">★ ${counts.astar} A*</span>
        <span class="paper-count a-rank">● ${counts.a} A</span>
      </div>
      <div class="faculty-card-arrow">→</div>
    </a>
  `;
}

function renderPubItem(pub) {
  const rankClass = pub.venue_rank === 'A*' ? 'astar' : 'a-rank';
  const titleHtml = pub.url
    ? `<a href="${escapeHtml(pub.url)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">${escapeHtml(pub.title)}</a>`
    : escapeHtml(pub.title);

  return `
    <div class="pub-item">
      <span class="pub-year">${pub.year}</span>
      <span class="pub-venue-badge ${rankClass}">${escapeHtml(pub.venue)}</span>
      <span class="pub-title">${titleHtml}</span>
      <span class="pub-score">${pub.adjusted_count.toFixed(2)}</span>
    </div>
  `;
}

// ── Faculty Detail Page ────────────────────────────────────
function renderFacultyDetailPage(app, instShort, dblpPid) {
  // Find the institution and faculty member
  const inst = data.institutions.find(i => i.short === instShort);
  if (!inst) {
    app.innerHTML = renderNotFound('Institution not found');
    return;
  }
  const faculty = inst.faculty.find(f => f.dblp_pid === dblpPid);
  if (!faculty) {
    app.innerHTML = renderNotFound('Faculty member not found');
    return;
  }

  const allPubs = faculty.publications || [];
  const score = allPubs.reduce((s, p) => s + p.adjusted_count, 0);
  const astarPubs = allPubs.filter(p => p.venue_rank === 'A*');
  const aPubs = allPubs.filter(p => p.venue_rank === 'A');

  // Area breakdown for this faculty member
  const areaMap = {};
  for (const pub of allPubs) {
    const code = pub.for_code || 'Unknown';
    if (!areaMap[code]) areaMap[code] = { code, papers: 0, astar: 0, a: 0, score: 0 };
    areaMap[code].papers++;
    areaMap[code].score += pub.adjusted_count;
    if (pub.venue_rank === 'A*') areaMap[code].astar++;
    else areaMap[code].a++;
  }
  const areas = Object.values(areaMap).sort((a, b) => b.papers - a.papers);
  const maxAreaPapers = Math.max(...areas.map(a => a.papers), 1);

  // FoR code descriptions
  const forDescriptions = {
    '4601': 'Applied Computing',
    '4602': 'Artificial Intelligence',
    '4603': 'Computer Vision and Multimedia',
    '4604': 'Cybersecurity and Privacy',
    '4605': 'Data Management and Data Science',
    '4606': 'Distributed Computing and Systems Software',
    '4607': 'Graphics, Augmented Reality and Games',
    '4608': 'Human-Centred Computing',
    '4609': 'Information Systems',
    '4610': 'Library and Information Studies',
    '4611': 'Machine Learning',
    '4612': 'Software Engineering',
    '4613': 'Theory of Computation',
    'CSE': 'Computer Science and Engineering',
  };

  // Venue breakdown
  const venueMap = {};
  for (const pub of allPubs) {
    const v = pub.venue;
    if (!venueMap[v]) venueMap[v] = { venue: v, rank: pub.venue_rank, count: 0, score: 0 };
    venueMap[v].count++;
    venueMap[v].score += pub.adjusted_count;
  }
  const venues = Object.values(venueMap).sort((a, b) => b.count - a.count);

  // Year-wise publication timeline
  const yearMap = {};
  for (const pub of allPubs) {
    if (!yearMap[pub.year]) yearMap[pub.year] = { astar: 0, a: 0 };
    if (pub.venue_rank === 'A*') yearMap[pub.year].astar++;
    else yearMap[pub.year].a++;
  }
  const years = Object.keys(yearMap).map(Number).sort();
  const maxYearPapers = Math.max(...years.map(y => yearMap[y].astar + yearMap[y].a), 1);

  const dblpUrl = `https://dblp.org/pid/${dblpPid}`;

  app.innerHTML = `
    <div class="bg-grid"></div>
    <div class="bg-glow bg-glow-1"></div>
    <div class="bg-glow bg-glow-2"></div>

    <div class="container faculty-detail-page">
      <button class="back-btn" id="back-btn">
        <span class="back-arrow">←</span> Back to Rankings
      </button>

      <div class="fd-hero animate-in">
        <div class="fd-hero-content">
          <div class="fd-avatar">${escapeHtml(faculty.name.charAt(0))}</div>
          <div class="fd-hero-info">
            <h1 class="fd-name">${escapeHtml(faculty.name)}</h1>
            <div class="fd-role">${escapeHtml(faculty.role)}</div>
            <div class="fd-institution">
              <span class="fd-inst-name">${escapeHtml(inst.name)}</span>
              <span class="fd-inst-short">${escapeHtml(inst.short)}</span>
            </div>
          </div>
          <div class="fd-hero-score">
            <div class="fd-score-value">${formatScore(score)}</div>
            <div class="fd-score-label">SPARK Score</div>
          </div>
        </div>
        <div class="fd-links">
          ${faculty.homepage ? `<a href="${escapeHtml(faculty.homepage)}" target="_blank" rel="noopener" class="fd-link">🏠 Homepage</a>` : ''}
          <a href="${escapeHtml(dblpUrl)}" target="_blank" rel="noopener" class="fd-link">📚 DBLP Profile</a>
        </div>
      </div>

      <div class="fd-stats-grid animate-in">
        <div class="fd-stat-card">
          <div class="fd-stat-number gold">${astarPubs.length}</div>
          <div class="fd-stat-desc">A* Papers</div>
        </div>
        <div class="fd-stat-card">
          <div class="fd-stat-number blue">${aPubs.length}</div>
          <div class="fd-stat-desc">A Papers</div>
        </div>
        <div class="fd-stat-card">
          <div class="fd-stat-number emerald">${allPubs.length}</div>
          <div class="fd-stat-desc">Total Papers</div>
        </div>
        <div class="fd-stat-card">
          <div class="fd-stat-number">${venues.length}</div>
          <div class="fd-stat-desc">Unique Venues</div>
        </div>
      </div>

      ${years.length > 0 ? `
      <section class="fd-section animate-in">
        <div class="section-header">
          <span class="section-icon">📈</span>
          <h2 class="section-title">Publication Timeline</h2>
        </div>
        <div class="fd-timeline">
          ${years.map(y => {
            const total = yearMap[y].astar + yearMap[y].a;
            const pct = (total / maxYearPapers) * 100;
            return `
              <div class="fd-timeline-row">
                <span class="fd-timeline-year">${y}</span>
                <div class="fd-timeline-bar-wrapper">
                  <div class="fd-timeline-bar astar" style="width: ${(yearMap[y].astar / maxYearPapers) * 100}%"></div>
                  <div class="fd-timeline-bar a-rank" style="width: ${(yearMap[y].a / maxYearPapers) * 100}%"></div>
                </div>
                <span class="fd-timeline-count">
                  ${yearMap[y].astar > 0 ? `<span class="paper-count astar">★${yearMap[y].astar}</span>` : ''}
                  ${yearMap[y].a > 0 ? `<span class="paper-count a-rank">●${yearMap[y].a}</span>` : ''}
                </span>
              </div>
            `;
          }).join('')}
        </div>
        <div class="fd-timeline-legend">
          <span class="paper-count astar">★ A*</span>
          <span class="paper-count a-rank">● A</span>
        </div>
      </section>` : ''}

      ${areas.length > 0 ? `
      <section class="fd-section animate-in">
        <div class="section-header">
          <span class="section-icon">🗂️</span>
          <h2 class="section-title">Research Areas</h2>
        </div>
        <div class="fd-areas-grid">
          ${areas.map(area => {
            const pct = (area.papers / maxAreaPapers) * 100;
            const desc = forDescriptions[area.code] || `FoR ${area.code}`;
            return `
              <div class="fd-area-card">
                <div class="fd-area-name">${escapeHtml(desc)}</div>
                <div class="area-bar-wrapper"><div class="area-bar mixed" style="width: ${pct}%"></div></div>
                <div class="fd-area-stats">
                  <span>${area.papers} papers</span>
                  <span>
                    ${area.astar > 0 ? `<span class="paper-count astar">★${area.astar}</span>` : ''}
                    ${area.a > 0 ? `<span class="paper-count a-rank">●${area.a}</span>` : ''}
                  </span>
                </div>
              </div>
            `;
          }).join('')}
        </div>
      </section>` : ''}

      ${venues.length > 0 ? `
      <section class="fd-section animate-in">
        <div class="section-header">
          <span class="section-icon">🏛️</span>
          <h2 class="section-title">Venue Breakdown</h2>
          <span class="section-subtitle">${venues.length} venues</span>
        </div>
        <div class="fd-venues-grid">
          ${venues.map(v => {
            const rankClass = v.rank === 'A*' ? 'astar' : 'a-rank';
            return `
              <div class="fd-venue-chip">
                <span class="pub-venue-badge ${rankClass}">${escapeHtml(v.venue)}</span>
                <span class="fd-venue-count">${v.count} paper${v.count > 1 ? 's' : ''}</span>
                <span class="fd-venue-score">${v.score.toFixed(2)}</span>
              </div>
            `;
          }).join('')}
        </div>
      </section>` : ''}

      <section class="fd-section animate-in">
        <div class="section-header">
          <span class="section-icon">📄</span>
          <h2 class="section-title">All Publications</h2>
          <span class="section-subtitle">${allPubs.length} papers</span>
        </div>
        <div class="fd-pub-list">
          ${allPubs.map(p => renderPubItem(p)).join('')}
        </div>
      </section>

      ${renderFooter()}
    </div>
  `;

  // Attach back button
  document.getElementById('back-btn')?.addEventListener('click', (e) => {
    e.preventDefault();
    goHome();
  });

  window.scrollTo(0, 0);
}

function renderNotFound(msg) {
  return `
    <div class="bg-grid"></div>
    <div class="container" style="padding-top: 10vh;">
      <div class="no-data">
        <div class="no-data-icon">😕</div>
        <h2 style="margin-bottom: 1rem;">${escapeHtml(msg)}</h2>
        <button class="back-btn" onclick="window.location.hash=''">← Back to Rankings</button>
      </div>
    </div>
  `;
}

function renderAreaBreakdown() {
  if (!data.institutions.length) return '';

  // Aggregate area data across all institutions
  const areaMap = {};
  for (const inst of data.institutions) {
    for (const area of inst.area_breakdown || []) {
      if (!areaMap[area.for_code]) {
        areaMap[area.for_code] = { ...area, papers: 0, papers_astar: 0, papers_a: 0, score: 0 };
      }
      areaMap[area.for_code].papers += area.papers;
      areaMap[area.for_code].papers_astar += area.papers_astar;
      areaMap[area.for_code].papers_a += area.papers_a;
      areaMap[area.for_code].score += area.score;
    }
  }

  const areas = Object.values(areaMap).sort((a, b) => b.papers - a.papers);
  const maxPapers = Math.max(...areas.map(a => a.papers), 1);

  return `
    <section class="section">
      <div class="section-header">
        <span class="section-icon">📊</span>
        <h2 class="section-title">Research Area Breakdown</h2>
        <span class="section-subtitle">${areas.length} areas</span>
      </div>
      <div class="area-grid">
        ${areas.map(area => {
          const pct = (area.papers / maxPapers) * 100;
          return `
            <div class="area-card animate-in">
              <div class="area-name">${escapeHtml(area.description)}</div>
              <div class="area-bar-wrapper">
                <div class="area-bar mixed" style="width: ${pct}%"></div>
              </div>
              <div class="area-stats">
                <span style="color: var(--text-secondary)">
                  ${area.papers} papers
                  (<span style="color: var(--accent-gold)">★${area.papers_astar}</span> /
                   <span style="color: var(--accent-blue)">●${area.papers_a}</span>)
                </span>
                <span style="color: var(--accent-emerald); font-family: var(--font-mono); font-size: 0.8rem;">
                  ${area.score.toFixed(1)}
                </span>
              </div>
            </div>
          `;
        }).join('')}
      </div>
    </section>
  `;
}

function renderConferenceExplorer() {
  const conferences = data.conferences || [];
  const pubCounts = getConferencePubCounts();

  // Split into A* and A
  const astarConfs = conferences.filter(c => c.rank === 'A*');
  const aConfs = conferences.filter(c => c.rank === 'A');

  const renderConfCards = (confs) => confs
    .map(conf => {
      const papers = pubCounts[conf.acronym] || 0;
      const hasP = papers > 0;
      return `
        <div class="conf-card ${hasP ? 'has-papers' : ''} animate-in">
          <div class="conf-card-header">
            <span class="conf-acronym">${escapeHtml(conf.acronym)}</span>
            <span class="conf-rank-badge ${conf.rank === 'A*' ? 'astar' : 'a-rank'}">
              ${conf.rank}
            </span>
          </div>
          <div class="conf-title">${escapeHtml(conf.title)}</div>
          <div class="conf-meta">
            <span>FoR: ${escapeHtml(conf.for_code || 'N/A')}</span>
            ${hasP ? `<span class="conf-papers">${papers} paper${papers > 1 ? 's' : ''}</span>` : ''}
            ${conf.dblp_key ? `<a href="https://dblp.org/db/conf/${escapeHtml(conf.dblp_key)}" target="_blank" rel="noopener" style="color: var(--text-muted);">DBLP ↗</a>` : ''}
          </div>
        </div>
      `;
    })
    .join('');

  return `
    <section class="section">
      <div class="section-header">
        <span class="section-icon">📚</span>
        <h2 class="section-title">Conference Explorer</h2>
        <span class="section-subtitle">${conferences.length} conferences tracked</span>
      </div>

      <h3 style="font-size: 1.1rem; margin-bottom: 1rem; color: var(--accent-gold);">
        ★ A* Conferences (${astarConfs.length})
      </h3>
      <div class="conf-grid" style="margin-bottom: 2rem;">
        ${renderConfCards(astarConfs)}
      </div>

      <h3 style="font-size: 1.1rem; margin-bottom: 1rem; color: var(--accent-blue);">
        ● A Conferences (${aConfs.length})
      </h3>
      <div class="conf-grid">
        ${renderConfCards(aConfs)}
      </div>
    </section>
  `;
}

function renderMethodology() {
  // List of CSRankings venues for comparison
  const csrankingsVenues = [
    'AAAI', 'IJCAI', 'CVPR', 'ECCV', 'ICCV', 'ICML', 'NeurIPS', 'ACL',
    'EMNLP', 'NAACL', 'SIGIR', 'WWW', 'KDD', 'SIGMOD', 'VLDB', 'ICDE',
    'PODS', 'OSDI', 'SOSP', 'PLDI', 'POPL', 'ISCA', 'MICRO', 'ASPLOS',
    'HPCA', 'CCS', 'Oakland', 'USENIX Security', 'NDSS', 'CHI', 'CSCW',
    'UbiComp', 'STOC', 'FOCS', 'SODA', 'MOBICOM', 'SIGCOMM', 'NSDI',
    'INFOCOM', 'CRYPTO', 'EUROCRYPT', 'FSE', 'ICSE', 'ASE', 'CAV',
  ];

  const icoreAcronyms = new Set((data.conferences || []).map(c => c.acronym));
  const csrSet = new Set(csrankingsVenues);
  const onlyICORE = [...icoreAcronyms].filter(a => !csrSet.has(a)).sort();
  const onlyCSR = csrankingsVenues.filter(a => !icoreAcronyms.has(a)).sort();
  const both = csrankingsVenues.filter(a => icoreAcronyms.has(a)).sort();

  return `
    <section class="section">
      <div class="methodology">
        <div class="section-header" style="margin-bottom: 1.5rem;">
          <span class="section-icon">📋</span>
          <h2 class="section-title">Methodology</h2>
        </div>

        <h3>How SPARK Works</h3>
        <p>
          SPARK ranks CS departments by counting faculty publications in top-tier conferences,
          using the <strong>ICORE ${data.conference_source || '2026'}</strong> ranking system as the
          authoritative source for which conferences are "top-tier."
        </p>

        <h3>Scoring</h3>
        <ul>
          <li>We use <strong>all ${data.total_conferences_tracked} ICORE A* and A conferences</strong> (not a hand-picked subset)</li>
          <li>Each paper is counted as <code>1.0</code> total, split equally among co-authors (adjusted count)</li>
          <li>A faculty member's score = sum of their adjusted counts across all matched papers</li>
          <li>An institution's score = sum of all faculty scores</li>
          <li>Publication window: <code>${data.year_range ? data.year_range[0] : 2015}–${data.year_range ? data.year_range[1] : 2025}</code></li>
        </ul>

        <h3>Data Sources</h3>
        <ul>
          <li><strong>Conference rankings</strong>: ICORE Portal (portal.core.edu.au) — ${data.total_conferences_astar || 0} A*, ${data.total_conferences_a || 0} A</li>
          <li><strong>Publications</strong>: DBLP (dblp.org) — matched by venue key</li>
          <li><strong>Faculty list</strong>: Manually curated with DBLP PIDs</li>
        </ul>

        <h3>SPARK vs CSRankings: Conference Coverage</h3>
        <p>
          CSRankings uses ~${csrankingsVenues.length} hand-picked conferences.
          SPARK uses all ${data.total_conferences_tracked} ICORE A*/A conferences.
          Here's the difference:
        </p>

        <table class="comparison-table">
          <thead>
            <tr>
              <th>Category</th>
              <th>Count</th>
              <th>Examples</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td style="color: var(--accent-emerald); font-weight: 600;">In Both</td>
              <td style="font-family: var(--font-mono);">${both.length}</td>
              <td>${both.slice(0, 8).join(', ')}${both.length > 8 ? '...' : ''}</td>
            </tr>
            <tr>
              <td style="color: var(--accent-gold); font-weight: 600;">ICORE Only (extra)</td>
              <td style="font-family: var(--font-mono);">${onlyICORE.length}</td>
              <td>${onlyICORE.slice(0, 8).join(', ')}${onlyICORE.length > 8 ? '...' : ''}</td>
            </tr>
            <tr>
              <td style="color: var(--accent-rose); font-weight: 600;">CSRankings Only</td>
              <td style="font-family: var(--font-mono);">${onlyCSR.length}</td>
              <td>${onlyCSR.join(', ') || 'None'}</td>
            </tr>
          </tbody>
        </table>

        <p style="font-size: 0.8rem; color: var(--text-muted); margin-top: 1rem;">
          Generated: ${data.generated_at || 'N/A'} · Data pipeline built with Python, DBLP API, and ICORE Portal.
          No CSRankings code was used.
        </p>
      </div>
    </section>
  `;
}

function renderFooter() {
  return `
    <footer class="footer">
      <p>
        SPARK — Scholarly Publication & Academic Ranking Knowledgebase ·
        Data sourced from <a href="https://dblp.org" target="_blank" rel="noopener">DBLP</a> and
        <a href="http://portal.core.edu.au/conf-ranks/" target="_blank" rel="noopener">ICORE</a> ·
        Built for transparent academic ranking
      </p>
    </footer>
  `;
}

// ── Event Listeners ────────────────────────────────────────
function attachEventListeners() {
  // Tab buttons
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      filters.activeTab = btn.dataset.tab;
      render();
    });
  });

  // Rank filter toggles
  document.querySelectorAll('.toggle-btn[data-rank]').forEach(btn => {
    btn.addEventListener('click', () => {
      filters.rankFilter = btn.dataset.rank;
      render();
    });
  });

  // Area filter
  const areaSelect = document.getElementById('area-filter');
  if (areaSelect) {
    areaSelect.addEventListener('change', () => {
      filters.areaFilter = areaSelect.value;
      render();
    });
  }

  // Search
  const searchInput = document.getElementById('search-input');
  if (searchInput) {
    let debounce = null;
    searchInput.addEventListener('input', () => {
      clearTimeout(debounce);
      debounce = setTimeout(() => {
        filters.searchQuery = searchInput.value;
        // Re-render just the ranking section for performance
        const section = document.getElementById('ranking-section');
        if (section) {
          section.outerHTML = renderRankingSection();
          // Re-attach institution row click listeners
          attachInstitutionListeners();
        }
      }, 200);
    });
    // Focus after render only on rankings tab
    if (filters.activeTab === 'rankings' && !document.activeElement?.closest('.faculty-card')) {
      searchInput.focus();
      searchInput.selectionStart = searchInput.value.length;
    }
  }

  // Institution rows
  attachInstitutionListeners();
}

function attachInstitutionListeners() {
  document.querySelectorAll('.inst-row').forEach(row => {
    row.addEventListener('click', () => {
      const instId = row.dataset.inst;
      if (expandedInstitution === instId) {
        expandedInstitution = null;
      } else {
        expandedInstitution = instId;
      }
      render();
    });
  });
}

// Faculty cards are now <a> links — no click listener needed

// ── Init ───────────────────────────────────────────────────
async function init() {
  const success = await loadData();
  if (success) {
    // Small delay for loading animation
    setTimeout(render, 300);
  } else {
    render();
  }
}

// Listen for hash changes (back/forward navigation)
window.addEventListener('hashchange', () => {
  render();
});

init();
