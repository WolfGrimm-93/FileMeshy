/**
 * Panel de confirmación de una sola vez, mostrado inmediatamente después de
 * crear un tenant. La contraseña inicial del admin del tenant NUNCA viaja
 * por esta API a propósito (decisión de seguridad documentada en el
 * backend) -- solo queda en los logs del contenedor `backend`. Este modal
 * deja clarísimo dónde buscarla, no intenta mostrarla ni pedirla.
 */
import { AlertTriangle } from 'lucide-react'
import { Modal } from '@/ui/modals/Modal'
import { Button } from '@/ui/buttons/Button'
import type { TenantCreateResult } from '../services/tenants.service'

interface TenantCredentialsModalProps {
  result: TenantCreateResult | null
  onClose: () => void
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-0.5 break-all font-mono text-sm text-foreground">{value}</p>
    </div>
  )
}

export function TenantCredentialsModal({ result, onClose }: TenantCredentialsModalProps) {
  return (
    <Modal isOpen={result !== null} onClose={onClose} title="Tenant creado" size="lg" closeOnOverlayClick={false}>
      {result && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-3 rounded-lg border border-gray-200 bg-gray-50 p-4 dark:border-gray-800 dark:bg-gray-900 sm:grid-cols-2">
            <Field label="Tenant ID" value={result.tenant_id} />
            <Field label="Slug" value={result.slug} />
            <Field label="Schema" value={result.schema_name} />
            <Field label="Email del admin" value={result.admin_email} />
          </div>

          <div className="flex gap-3 rounded-lg border border-yellow-300 bg-yellow-50 p-4 text-sm text-yellow-800 dark:border-yellow-900 dark:bg-yellow-950/30 dark:text-yellow-300">
            <AlertTriangle className="size-5 shrink-0" />
            <div>
              <p className="font-medium">La contraseña inicial no viaja por acá por seguridad.</p>
              <p className="mt-1">
                Buscala en los logs del contenedor backend del servidor y entregala al cliente por un canal seguro:
              </p>
              <pre className="mt-2 overflow-x-auto rounded bg-black/80 p-2 font-mono text-xs text-yellow-100">
                docker logs {'<contenedor>'}-backend | grep {result.admin_email}
              </pre>
            </div>
          </div>

          <div className="flex justify-end">
            <Button type="button" variant="primary" onClick={onClose}>
              Entendido
            </Button>
          </div>
        </div>
      )}
    </Modal>
  )
}
