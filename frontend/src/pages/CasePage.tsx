import { Link, useParams } from 'react-router-dom'
import { api, ApiError } from '../api'
import { ErrorState, StateView } from '../components/ui'
import { useAsync } from '../lib/useAsync'
import RunView from '../run/RunView'

export default function CasePage() {
  const { slug = '' } = useParams()
  const { data, error, loading, reload } = useAsync(() => api.showcaseCase(slug), [slug])

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
  return <RunView result={data} events={data.trace} live={false} />
}
