import { useState } from 'react'

export default function Login({ onLogin, message = '' }) {
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      await onLogin(identifier, password)
      setPassword('')
    } catch (issue) {
      setError(issue.message)
    } finally {
      setBusy(false)
    }
  }

  return <main className="loginShell">
    <section className="loginStory" aria-label="About CaseLedger">
      <div className="brand loginBrand"><div className="brandIcon">C</div><div><strong>CaseLedger</strong><span>COURT CASE TRACKER</span></div></div>
      <div className="loginStoryContent">
        <span className="eyebrow light">A CLEARER CASE HISTORY</span>
        <h1>Every case.<br />In good order.</h1>
        <p>One place for the people, hearings, and decisions that shape each case.</p>
        <div className="loginIllustration" aria-hidden="true">
          <svg viewBox="0 0 440 270" fill="none">
            <circle cx="220" cy="126" r="108" stroke="currentColor" opacity=".16" />
            <circle cx="220" cy="126" r="83" stroke="currentColor" opacity=".12" />
            <path d="M146 96L220 52L294 96H146ZM153 184H287M141 197H299M134 209H306" stroke="currentColor" strokeWidth="2" />
            <path d="M160 108H180M160 173H180M166 108V173M174 108V173M210 108H230M210 173H230M216 108V173M224 108V173M260 108H280M260 173H280M266 108V173M274 108V173" stroke="currentColor" strokeWidth="2" />
            <path d="M83 131H116M324 131H357M220 223V247" stroke="currentColor" opacity=".5" strokeDasharray="4 5" />
            <rect x="34" y="110" width="50" height="42" rx="7" stroke="currentColor" opacity=".7" />
            <path d="M45 122H72M45 131H66M45 140H62" stroke="currentColor" opacity=".7" />
            <rect x="356" y="110" width="50" height="42" rx="7" stroke="currentColor" opacity=".7" />
            <path d="M368 121L375 128L390 117M368 138H393" stroke="currentColor" opacity=".7" />
            <circle cx="220" cy="253" r="5" fill="currentColor" />
          </svg>
        </div>
        <div className="loginFeatures"><span>Cases</span><span>Hearings</span><span>Judgments</span></div>
      </div>
      <p className="loginStoryFooter">COURT CASE &amp; JUDGMENT TRACKING SYSTEM</p>
    </section>

    <section className="loginFormArea">
      <div className="loginCard">
        <span className="eyebrow">YOUR CASE WORKSPACE</span>
        <h2>Welcome back.</h2>
        <p className="loginIntro">Sign in to continue to your case register.</p>
        <form onSubmit={submit} className="loginForm">
          <label className="field" htmlFor="login-identifier"><span>Username or email</span>
            <input id="login-identifier" name="username" autoComplete="username" autoCapitalize="none" spellCheck={false}
              placeholder="Enter your username or email" value={identifier} onChange={(event) => setIdentifier(event.target.value)}
              maxLength={254} required disabled={busy} />
          </label>
          <label className="field" htmlFor="login-password"><span>Password</span>
            <div className="loginPasswordField"><input id="login-password" name="password" type={showPassword ? 'text' : 'password'}
              autoComplete="current-password" placeholder="Enter your password" value={password}
              onChange={(event) => setPassword(event.target.value)} maxLength={256} required disabled={busy} />
              <button type="button" className="passwordToggle" aria-label={showPassword ? 'Hide password' : 'Show password'}
                aria-pressed={showPassword} onClick={() => setShowPassword((value) => !value)}>{showPassword ? 'Hide' : 'Show'}</button>
            </div>
          </label>
          {(error || message) && <div className="loginError" role="alert">{error || message}</div>}
          <button type="submit" className="button primary loginSubmit" disabled={busy}>
            <span>{busy ? 'Signing in…' : 'Sign in'}</span><span aria-hidden="true">→</span>
          </button>
        </form>
        <div className="loginFootnote"><span className="loginFootnoteLine" /><p>Academic demonstration with fictional case records.</p></div>
      </div>
      <footer className="loginPageFooter">CASELEDGER <span>Organized records. Clear decisions.</span></footer>
    </section>
  </main>
}
