/**
 * Hook para gestionar el título del documento (SEO)
 * Actualiza automáticamente el título de la página
 */

import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { routeConfig } from '../routes/routes.config'

const DEFAULT_TITLE = 'FileMeshy'
const TITLE_SUFFIX = ' - FileMeshy'

/**
 * Hook para establecer el título del documento
 * @param title - Título personalizado (opcional)
 */
export function useDocumentTitle(title?: string) {
  const location = useLocation()

  useEffect(() => {
    // Si se proporciona un título personalizado, usarlo
    if (title) {
      document.title = title.includes('FileMeshy') ? title : `${title}${TITLE_SUFFIX}`
      return
    }

    // Buscar el título en la configuración de rutas
    const route = routeConfig.find((r) => r.path === location.pathname)
    
    if (route?.meta?.title) {
      document.title = route.meta.title
    } else if (route?.title) {
      document.title = `${route.title}${TITLE_SUFFIX}`
    } else {
      document.title = DEFAULT_TITLE
    }
  }, [title, location.pathname])
}

/**
 * Hook para establecer meta tags (descripción, keywords, etc.)
 */
export function useDocumentMeta() {
  const location = useLocation()

  useEffect(() => {
    const route = routeConfig.find((r) => r.path === location.pathname)
    
    if (!route?.meta) return

    // Actualizar descripción
    if (route.meta.description) {
      let metaDescription = document.querySelector<HTMLMetaElement>('meta[name="description"]')
      if (!metaDescription) {
        metaDescription = document.createElement('meta')
        metaDescription.setAttribute('name', 'description')
        document.head.appendChild(metaDescription)
      }
      metaDescription.setAttribute('content', route.meta.description)
    }

    // Actualizar keywords
    if (route.meta.keywords) {
      let metaKeywords = document.querySelector<HTMLMetaElement>('meta[name="keywords"]')
      if (!metaKeywords) {
        metaKeywords = document.createElement('meta')
        metaKeywords.setAttribute('name', 'keywords')
        document.head.appendChild(metaKeywords)
      }
      metaKeywords.setAttribute('content', route.meta.keywords.join(', '))
    }

    // Actualizar Open Graph title
    if (route.meta.title) {
      let ogTitle = document.querySelector<HTMLMetaElement>('meta[property="og:title"]')
      if (!ogTitle) {
        ogTitle = document.createElement('meta')
        ogTitle.setAttribute('property', 'og:title')
        document.head.appendChild(ogTitle)
      }
      ogTitle.setAttribute('content', route.meta.title)
    }

    // Actualizar Open Graph description
    if (route.meta.description) {
      let ogDescription = document.querySelector<HTMLMetaElement>('meta[property="og:description"]')
      if (!ogDescription) {
        ogDescription = document.createElement('meta')
        ogDescription.setAttribute('property', 'og:description')
        document.head.appendChild(ogDescription)
      }
      ogDescription.setAttribute('content', route.meta.description)
    }

    // Actualizar Open Graph image
    if (route.meta.ogImage) {
      let ogImage = document.querySelector<HTMLMetaElement>('meta[property="og:image"]')
      if (!ogImage) {
        ogImage = document.createElement('meta')
        ogImage.setAttribute('property', 'og:image')
        document.head.appendChild(ogImage)
      }
      ogImage.setAttribute('content', route.meta.ogImage)
    }
  }, [location.pathname])
}

/**
 * Hook combinado que gestiona título y meta tags
 * @param title - Título personalizado (opcional)
 */
export function useSEO(title?: string) {
  useDocumentTitle(title)
  useDocumentMeta()
}
