/**
 * Servicio de tenants del panel de plataforma.
 *
 * Tipos LOCALES a este módulo a propósito -- no importa `FileOut` ni
 * ningún tipo del resto de la app, este panel está deliberadamente
 * desacoplado (ver comentario de `platformAdmin.api.ts`). Contrato fijado
 * en conjunto con el backend (Ronda 8, endpoints `/api/v1/platform/tenants*`
 * -- ver `app/platform/router.py` / `app/platform/schemas.py`, construido en
 * paralelo por otro agente sobre esos mismos archivos).
 */
import platformAdminApi from './platformAdmin.api'

export interface TenantListItem {
  id: string
  slug: string
  schema_name: string
  company_name: string
  plan: string
  is_active: boolean
  created_at: string
}

export interface TenantCreatePayload {
  slug: string
  schema_name: string
  company_name: string
  plan?: string
}

export interface TenantCreateResult {
  tenant_id: string
  slug: string
  schema_name: string
  admin_email: string
}

export interface TenantUpdatePayload {
  is_active?: boolean
  plan?: string
}

class TenantsService {
  private basePath = '/tenants'

  /** GET /platform/tenants -- lista completa (sin paginación en el contrato). */
  async list(): Promise<TenantListItem[]> {
    const response = await platformAdminApi.get<TenantListItem[]>(this.basePath)
    return response.data
  }

  /** GET /platform/tenants/{id} -- 404 si no existe. */
  async get(tenantId: string): Promise<TenantListItem> {
    const response = await platformAdminApi.get<TenantListItem>(`${this.basePath}/${tenantId}`)
    return response.data
  }

  /**
   * POST /platform/tenants -- alta de un tenant nuevo. La contraseña inicial
   * del admin NUNCA viaja acá (ver `TenantCreateResult`, no tiene ese campo
   * a propósito) -- queda solo en los logs del contenedor backend.
   */
  async create(payload: TenantCreatePayload): Promise<TenantCreateResult> {
    const response = await platformAdminApi.post<TenantCreateResult>(this.basePath, payload)
    return response.data
  }

  /** PATCH /platform/tenants/{id} -- al menos uno de is_active/plan. */
  async update(tenantId: string, payload: TenantUpdatePayload): Promise<TenantListItem> {
    const response = await platformAdminApi.patch<TenantListItem>(`${this.basePath}/${tenantId}`, payload)
    return response.data
  }
}

export const tenantsService = new TenantsService()
