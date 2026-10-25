import { Link, useParams } from 'react-router-dom'
import { api, ApiError } from '../api'
import { ErrorState, StateView } from '../components/ui'
import { useAsync } from '../lib/useAsync'
import RunView from '../run/RunView'
import type { ShowcaseSummary } from '../types'

export default function CasePage() {
  const { slug = '' } = useParams()
  const { data, error, loading, reload } = useAsync(() => api.showcaseCase(slug), [slug])
  // The decision year lives in the showcase list; the header shows it next to the court.
  const list = useAsync(() => api.showcase().catch(() => [] as ShowcaseSummary[]), [])
  const year = list.data?.find((c) => c.slug === slug)?.year ?? null

  if (loading) return <StateView kind="loading" title="Opening the case" />
  if (error) {
    if (error instanceof ApiError && error.status === 404)
      return (
        <StateView
          kind="empty"
          title="Case not found"
          body={error.detail || 'There is no showcase case at this address.'}
          action={
            <Link className="btn btn--sm" to="/">
              All cases
            </Link>
          }
        />
      )
    return <ErrorState error={error} onRetry={reload} title="Could not open this case" />
  }
  if (!data) return null
  return <RunView result={data} events={data.trace} live={false} year={year} />
}
