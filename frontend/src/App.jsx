import { useEffect, useMemo, useState } from 'react'
import { api } from './api'
import Login from './Login'

const today = () => {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}
const dateText = (value) => value
  ? new Date(`${value.slice(0, 10)}T00:00:00`).toLocaleDateString('en-IN', {
      day: '2-digit', month: 'short', year: 'numeric',
    })
  : 'Not set'

const initialForms = {
  case: () => ({ case_number: '', title: '', court_name: '', filed_on: today(), assigned_judge_id: '', parent_case_id: '' }),
  judge: () => ({ full_name: '', designation: '', court_name: '' }),
  party: () => ({ party_name: '', party_type: 'Person' }),
  attach: () => ({ party_id: '', party_role: 'Petitioner' }),
  hearing: () => ({ judge_id: '', hearing_date: today(), purpose: '', hearing_status: 'Scheduled' }),
  judgment: () => ({ judgment_date: today(), outcome: '', summary: '', document_url: '' }),
}

const formTitles = {
  case: 'Register a case', judge: 'Add a judge', party: 'Add a party',
  attach: 'Link a party', hearing: 'Record a hearing', judgment: 'Record a judgment',
}

function Badge({ status }) {
  return <span className={`badge ${status === 'Disposed' ? 'disposed' : status === 'Pending' ? 'pending' : 'neutral'}`}>{status}</span>
}

function Empty({ title, text }) {
  return <div className="empty"><div className="emptyMark">∅</div><strong>{title}</strong><p>{text}</p></div>
}

function FormField({ label, children }) {
  return <label className="field"><span>{label}</span>{children}</label>
}

function Modal({ kind, form, setForm, onClose, onSubmit, busy, judges, parties, cases }) {
  if (!kind) return null
  const set = (key) => (event) => setForm((old) => ({ ...old, [key]: event.target.value }))
  const input = (key, label, type = 'text', required = true) => (
    <FormField label={label}><input type={type} value={form[key] ?? ''} onChange={set(key)} required={required} /></FormField>
  )
  const select = (key, label, items, valueKey, labelKey, placeholder = 'Select an option') => (
    <FormField label={label}><select value={form[key] ?? ''} onChange={set(key)} required>
      <option value="">{placeholder}</option>
      {items.map((item) => <option value={item[valueKey]} key={item[valueKey]}>{item[labelKey]}</option>)}
    </select></FormField>
  )
  return <div className="modalBackdrop" onMouseDown={onClose}>
    <div className="modal" role="dialog" aria-modal="true" aria-label={formTitles[kind]} onMouseDown={(event) => event.stopPropagation()}>
      <div className="modalHeader"><div><span className="eyebrow">NEW RECORD</span><h2>{formTitles[kind]}</h2></div><button className="closeButton" type="button" onClick={onClose} aria-label="Close">×</button></div>
      <form onSubmit={onSubmit} className="modalForm">
        {kind === 'case' && <>
          <div className="twoCols">{input('case_number', 'Case number')}{input('filed_on', 'Filing date', 'date')}</div>
          {input('title', 'Case title')}{input('court_name', 'Court name')}
          {select('assigned_judge_id', 'Assigned judge', judges, 'judge_id', 'full_name')}
          <FormField label="Parent case for an appeal, optional"><select value={form.parent_case_id ?? ''} onChange={set('parent_case_id')}>
            <option value="">Original case</option>
            {cases.map((item) => <option value={item.case_id} key={item.case_id}>{item.case_number} · {item.title}</option>)}
          </select></FormField>
        </>}
        {kind === 'judge' && <>{input('full_name', 'Full name')}{input('designation', 'Designation')}{input('court_name', 'Court name')}</>}
        {kind === 'party' && <>{input('party_name', 'Party name')}<FormField label="Party type"><select value={form.party_type} onChange={set('party_type')}><option>Person</option><option>Organization</option></select></FormField></>}
        {kind === 'attach' && <>{select('party_id', 'Party', parties, 'party_id', 'party_name')}<FormField label="Role in this case"><select value={form.party_role} onChange={set('party_role')}><option>Petitioner</option><option>Respondent</option><option>Appellant</option></select></FormField></>}
        {kind === 'hearing' && <>{input('hearing_date', 'Hearing date', 'date')}{select('judge_id', 'Judge', judges, 'judge_id', 'full_name')}{input('purpose', 'Purpose')}<FormField label="Status"><select value={form.hearing_status} onChange={set('hearing_status')}><option>Scheduled</option><option>Held</option><option>Adjourned</option><option>Cancelled</option></select></FormField></>}
        {kind === 'judgment' && <>{input('judgment_date', 'Judgment date', 'date')}{input('outcome', 'Outcome')}<FormField label="Summary"><textarea value={form.summary} onChange={set('summary')} rows="4" required /></FormField>{input('document_url', 'Document link, optional', 'url', false)}<p className="formHint">Saving a judgment changes this case to Disposed through the MySQL trigger.</p></>}
        <div className="modalActions"><button className="button secondary" type="button" onClick={onClose}>Cancel</button><button className="button primary" type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save record'}</button></div>
      </form>
    </div>
  </div>
}

function Workspace({ user, onLogout }) {
  const [screen, setScreen] = useState('overview')
  const [dashboard, setDashboard] = useState(null)
  const [cases, setCases] = useState([])
  const [judges, setJudges] = useState([])
  const [parties, setParties] = useState([])
  const [pending, setPending] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [modal, setModal] = useState(null)
  const [form, setForm] = useState({})
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('All')
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [signingOut, setSigningOut] = useState(false)

  async function signOut() {
    setSigningOut(true)
    try { await onLogout() }
    catch (issue) { setError(issue.message) }
    finally { setSigningOut(false) }
  }

  async function refresh(nextSelected = selectedId) {
    try {
      const [nextDashboard, nextCases, nextJudges, nextParties, nextPending] = await Promise.all([
        api('/dashboard'), api('/cases'), api('/judges'), api('/parties'), api('/reports/pending'),
      ])
      setDashboard(nextDashboard)
      setCases(nextCases)
      setJudges(nextJudges)
      setParties(nextParties)
      setPending(nextPending)
      setError('')
      if (nextSelected) {
        setDetail(await api(`/cases/${nextSelected}`))
      }
    } catch (issue) {
      setError(issue.message)
    }
  }

  useEffect(() => { refresh(null) }, [])

  async function selectCase(id) {
    setSelectedId(id)
    setScreen('cases')
    try {
      setDetail(await api(`/cases/${id}`))
      setError('')
    } catch (issue) {
      setError(issue.message)
    }
  }

  function showModal(kind, values = {}) {
    setForm({ ...initialForms[kind](), ...values })
    setModal(kind)
    setNotice('')
  }

  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      let path = ''
      let payload = { ...form }
      if (modal === 'case') {
        path = '/cases'
        payload.assigned_judge_id = Number(payload.assigned_judge_id)
        payload.parent_case_id = payload.parent_case_id ? Number(payload.parent_case_id) : null
      } else if (modal === 'judge') path = '/judges'
      else if (modal === 'party') path = '/parties'
      else if (modal === 'attach') {
        path = `/cases/${selectedId}/parties`
        payload.party_id = Number(payload.party_id)
      } else if (modal === 'hearing') {
        path = `/cases/${selectedId}/hearings`
        payload.judge_id = Number(payload.judge_id)
      } else if (modal === 'judgment') {
        path = `/cases/${selectedId}/judgment`
        payload.document_url = payload.document_url || null
      }
      const created = await api(path, { method: 'POST', body: JSON.stringify(payload) })
      setModal(null)
      setNotice(`${formTitles[modal]} saved.`)
      const nextSelected = created.case_id && modal === 'case' ? created.case_id : selectedId
      if (modal === 'case') {
        setSelectedId(nextSelected)
        setScreen('cases')
      }
      await refresh(nextSelected)
    } catch (issue) {
      setError(issue.message)
    } finally {
      setBusy(false)
    }
  }

  const visibleCases = useMemo(() => cases.filter((item) => {
    const matchesText = `${item.case_number} ${item.title}`.toLowerCase().includes(search.toLowerCase())
    return matchesText && (statusFilter === 'All' || item.case_status === statusFilter)
  }), [cases, search, statusFilter])

  const nav = [
    ['overview', 'Overview', '01'], ['cases', 'Cases', '02'],
    ['pending', 'Pending report', '03'], ['model', 'Data model', '04'],
  ]

  return <div className="appShell">
    <aside className="sidebar">
      <div className="brand"><div className="brandIcon">C</div><div><strong>CaseLedger</strong><span>COURT CASE TRACKER</span></div></div>
      <div className="sidebarDivider" />
      <div className="navLabel">WORKSPACE</div>
      <nav>{nav.map(([id, label, number]) => <button key={id} className={`navItem ${screen === id ? 'active' : ''}`} onClick={() => setScreen(id)}><span className="navNumber">{number}</span>{label}</button>)}</nav>
      <div className="sidebarBottom"><div className="signedInUser"><span className="userAvatar">{user.display_name.charAt(0)}</span><div><strong>{user.display_name}</strong><small>{user.email}</small></div></div><button className="logoutButton" type="button" onClick={signOut} disabled={signingOut}>{signingOut ? 'Signing out…' : 'Sign out'}</button><small className="sidebarLabNote">Local lab project · Fictional records</small></div>
    </aside>

    <main className="mainArea">
      <header className="topbar"><div><span className="eyebrow">DATABASE MANAGEMENT SYSTEM</span><h1>{nav.find(([id]) => id === screen)?.[1]}</h1></div><div className="topActions"><span className="labTag">MINI PROJECT</span><button className="button primary" onClick={() => showModal('case')}>+ New case</button></div></header>
      {error && <div className="alert error"><strong>Action needed</strong><span>{error}</span><button onClick={() => setError('')} aria-label="Dismiss">×</button></div>}
      {notice && <div className="alert success"><strong>Saved</strong><span>{notice}</span><button onClick={() => setNotice('')} aria-label="Dismiss">×</button></div>}

      {screen === 'overview' && <>
        <section className="hero"><div><span className="eyebrow light">CASE MANAGEMENT AT A GLANCE</span><h2>Every case has a clear history.</h2><p>Track hearings, judgments, parties, and the path from an original case through its appeals.</p><button className="button lightButton" onClick={() => setScreen('cases')}>Explore cases <span>→</span></button></div><div className="heroMark"><span>CASE</span><strong>→</strong><span>APPEAL</span><strong>→</strong><span>REVIEW</span></div></section>
        <section className="statsGrid">
          {[
            ['Total cases', dashboard?.total_cases ?? '—', 'All registered cases'],
            ['Pending', dashboard?.pending_cases ?? '—', 'Awaiting judgment'],
            ['Disposed', dashboard?.disposed_cases ?? '—', 'Judgment recorded'],
            ['Over six months', dashboard?.old_pending ?? '—', 'From the MySQL view'],
          ].map(([label, value, hint]) => <div className="statCard" key={label}><span>{label}</span><strong>{value}</strong><small>{hint}</small></div>)}
        </section>
        <section className="setupBar"><div><span className="eyebrow">QUICK SETUP</span><strong>Build the case register</strong><p>Add a judge and parties before linking them to cases.</p></div><div><button className="button secondary" onClick={() => showModal('judge')}>+ Judge</button><button className="button secondary" onClick={() => showModal('party')}>+ Party</button></div></section>
        <section className="panel"><div className="panelHead"><div><span className="eyebrow">RECENT ACTIVITY</span><h2>Case register</h2></div><button className="textButton" onClick={() => setScreen('cases')}>View all cases →</button></div>
          {cases.length ? <div className="tableWrap"><table><thead><tr><th>Case number</th><th>Title</th><th>Filed</th><th>Status</th></tr></thead><tbody>{cases.slice(0, 5).map((item) => <tr key={item.case_id} onClick={() => selectCase(item.case_id)}><td className="strongCell">{item.case_number}</td><td>{item.title}</td><td>{dateText(item.filed_on)}</td><td><Badge status={item.case_status} /></td></tr>)}</tbody></table></div> : <Empty title="No cases yet" text="Register a judge first, then create the first case." />}
        </section>
      </>}

      {screen === 'cases' && <div className="casesLayout"><section className="panel caseListPanel"><div className="panelHead"><div><span className="eyebrow">CASE REGISTER</span><h2>All cases <span className="countPill">{visibleCases.length}</span></h2></div></div><div className="filters"><input placeholder="Search number or title" value={search} onChange={(event) => setSearch(event.target.value)} aria-label="Search cases" /><select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} aria-label="Filter case status"><option>All</option><option>Pending</option><option>Disposed</option></select></div><div className="caseItems">{visibleCases.map((item) => <button className={`caseItem ${selectedId === item.case_id ? 'selected' : ''}`} key={item.case_id} onClick={() => selectCase(item.case_id)}><span className="caseItemTop"><strong>{item.case_number}</strong><Badge status={item.case_status} /></span><span className="caseItemTitle">{item.title}</span><span className="caseItemMeta">{item.court_name} · {dateText(item.filed_on)}</span></button>)}{!visibleCases.length && <Empty title="No matching cases" text="Try another search or add a case." />}</div></section>
        <section className="panel detailPanel">{detail && selectedId === detail.case.case_id ? <>
          <div className="detailHeader"><span className="eyebrow">CASE FILE · {detail.case.case_number}</span><Badge status={detail.case.case_status} /><h2>{detail.case.title}</h2><p>{detail.case.court_name} · Filed {dateText(detail.case.filed_on)}</p></div>
          <div className="detailFacts"><div><span>Assigned judge</span><strong>{detail.case.judge_name}</strong></div><div><span>Case type</span><strong>{detail.case.parent_case_id ? 'Appeal' : 'Original case'}</strong></div></div>
          <div className="detailActions"><button className="smallButton" onClick={() => showModal('case', { parent_case_id: detail.case.case_id })}>+ Appeal</button><button className="smallButton" onClick={() => showModal('attach')}>+ Party</button><button className="smallButton" onClick={() => showModal('hearing', { judge_id: detail.case.assigned_judge_id })}>+ Hearing</button>{!detail.judgment && <button className="smallButton accent" onClick={() => showModal('judgment')}>+ Judgment</button>}</div>
          <div className="detailSection"><div className="sectionTitle"><h3>Appeal chain</h3><span>{detail.appeal_chain.length} linked cases</span></div><div className="chain">{detail.appeal_chain.map((item, index) => <button key={item.case_id} className={`chainItem ${item.case_id === selectedId ? 'current' : ''}`} onClick={() => selectCase(item.case_id)}><span className="chainIndex">{String(index + 1).padStart(2, '0')}</span><span><strong>{item.case_number}</strong><small>{item.title}</small></span><Badge status={item.case_status} /></button>)}</div></div>
          <div className="detailSection"><div className="sectionTitle"><h3>Parties</h3><span>{detail.parties.length} linked</span></div>{detail.parties.length ? <div className="simpleList">{detail.parties.map((item) => <div key={item.party_id}><span><strong>{item.party_name}</strong><small>{item.party_type}</small></span><span className="roleTag">{item.party_role}</span></div>)}</div> : <p className="muted">No parties linked yet.</p>}</div>
          <div className="detailSection"><div className="sectionTitle"><h3>Hearing history</h3><span>{detail.hearings.length} entries</span></div>{detail.hearings.length ? <div className="simpleList">{detail.hearings.map((item) => <div key={item.hearing_id}><span><strong>{item.purpose}</strong><small>{dateText(item.hearing_date)} · {item.judge_name}</small></span><span className="roleTag">{item.hearing_status}</span></div>)}</div> : <p className="muted">No hearings recorded yet.</p>}</div>
          <div className="detailSection"><div className="sectionTitle"><h3>Judgment</h3></div>{detail.judgment ? <div className="judgmentCard"><span>{dateText(detail.judgment.judgment_date)}</span><strong>{detail.judgment.outcome}</strong><p>{detail.judgment.summary}</p>{detail.judgment.document_url && <a href={detail.judgment.document_url} target="_blank" rel="noreferrer">Open document link →</a>}</div> : <p className="muted">No judgment has been recorded for this case.</p>}</div>
        </> : <Empty title="Select a case" text="Choose a record on the left to see its history, parties, and appeals." />}</section></div>}

      {screen === 'pending' && <section className="panel"><div className="panelHead"><div><span className="eyebrow">MYSQL VIEW</span><h2>Pending for more than six months</h2><p className="muted">A live report based on filing date and case status.</p></div><div className="reportCount">{pending.length}<span>CASES</span></div></div>{pending.length ? <div className="tableWrap"><table><thead><tr><th>Case number</th><th>Title</th><th>Court</th><th>Judge</th><th>Filed</th></tr></thead><tbody>{pending.map((item) => <tr key={item.case_id} onClick={() => selectCase(item.case_id)}><td className="strongCell">{item.case_number}</td><td>{item.title}</td><td>{item.court_name}</td><td>{item.judge_name}</td><td>{dateText(item.filed_on)}</td></tr>)}</tbody></table></div> : <Empty title="No long pending cases" text="The view currently has no cases matching its six month rule." />}</section>}

      {screen === 'model' && <div className="modelPage"><section className="panel"><span className="eyebrow">FROM DESIGN TO SQL</span><h2>One clear database model</h2><p className="muted">The project follows the lab sequence from a conceptual ER model to six normalized tables and physical MySQL statements.</p><div className="processFlow">{['ER model', 'Draft tables', 'Normalization', 'Final schema', 'SQL tables'].map((step, index) => <div key={step}><span>{String(index + 1).padStart(2, '0')}</span><strong>{step}</strong></div>)}</div></section><div className="modelGrid">{[
        ['CASES', 'Original cases and appeals. An appeal points to its parent case.'],
        ['JUDGES', 'The judge assigned to a case or conducting a hearing.'],
        ['HEARINGS', 'Several dated hearings can belong to one case.'],
        ['JUDGMENTS', 'At most one judgment per case in this lab scope.'],
        ['PARTIES', 'A person or organization stored once.'],
        ['CASE_PARTIES', 'The role linking a party to a case.'],
      ].map(([name, description], index) => <div className="modelCard" key={name}><span>TABLE {String(index + 1).padStart(2, '0')}</span><h3>{name}</h3><p>{description}</p></div>)}</div><section className="panel modelNote"><h3>What to demonstrate in the viva</h3><p><strong>Many to many:</strong> CASE_PARTIES resolves the case and party relationship. <strong>Recursion:</strong> parent_case_id links appeals. <strong>Trigger:</strong> a judgment disposes its case. <strong>View:</strong> the pending report stays current.</p><div className="modelActions"><button className="button secondary" onClick={() => showModal('judge')}>+ Add judge</button><button className="button secondary" onClick={() => showModal('party')}>+ Add party</button></div></section></div>}
    </main>
    <Modal kind={modal} form={form} setForm={setForm} onClose={() => setModal(null)} onSubmit={submit} busy={busy} judges={judges} parties={parties} cases={cases} />
  </div>
}

export default function App() {
  const [user, setUser] = useState(null)
  const [checking, setChecking] = useState(true)
  const [message, setMessage] = useState('')

  useEffect(() => {
    let active = true
    api('/auth/me').then((account) => { if (active) setUser(account) })
      .catch((issue) => { if (active && issue.status !== 401) setMessage(issue.message) })
      .finally(() => { if (active) setChecking(false) })
    const expired = () => { setUser(null); setMessage('Your session has ended. Sign in again.') }
    window.addEventListener('caseledger:unauthorized', expired)
    return () => { active = false; window.removeEventListener('caseledger:unauthorized', expired) }
  }, [])

  async function login(identifier, password) {
    const account = await api('/auth/login', { method: 'POST', body: JSON.stringify({ identifier, password }) })
    setMessage('')
    setUser(account)
  }

  async function logout() {
    await api('/auth/logout', { method: 'POST' })
    setUser(null)
    setMessage('')
  }

  if (checking) return <div className="sessionLoading" role="status"><div className="brandIcon">C</div><p>Opening CaseLedger…</p></div>
  if (!user) return <Login onLogin={login} message={message} />
  return <Workspace user={user} onLogout={logout} />
}
