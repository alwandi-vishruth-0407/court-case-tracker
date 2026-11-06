export async function api(path, options = {}) {
  let response
  try {
    response = await fetch(`/api${path}`, {
      credentials: 'same-origin',
      cache: 'no-store',
      ...options,
      headers: { 'Content-Type': 'application/json', 'X-CaseLedger-Request': '1', ...options.headers },
    })
  } catch {
    throw new Error('The server could not be reached. Check your connection and try again shortly.')
  }
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = Array.isArray(body.detail)
      ? body.detail.map((item) => item.msg).join('; ')
      : body.detail
    if (response.status === 401 && !path.startsWith('/auth/')) {
      window.dispatchEvent(new Event('caseledger:unauthorized'))
    }
    const issue = new Error(detail || 'The request could not be completed.')
    issue.status = response.status
    throw issue
  }
  return body
}
