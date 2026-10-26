import { Link } from 'react-router-dom'
import { StateView } from '../components/ui'

export default function NotFoundPage() {
  return (
    <div className="container page-enter">
      <StateView
        kind="empty"
        title="This page does not exist"
        body="The link may be mistyped, or the run may have expired."
        action={
          <Link className="btn btn--sm" to="/">
            Back to cases
          </Link>
        }
      />
    </div>
  )
}
