import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Heart, Shield, Database, Eye, Lock, UserCheck, Cookie, Mail } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/ui/cards/Card'
import { Button } from '@/ui/buttons/Button'
import { Separator } from '@/ui/dividers/Separator'

const sections = [
  {
    icon: Database,
    title: 'Datos que Recopilamos',
    content: [
      'Recopilamos información de cuenta al registrar usuarios: nombre completo, dirección de correo electrónico, número de teléfono y preferencias de configuración del sistema (tema visual, notificaciones).',
      'Almacenamos los archivos y carpetas que el usuario sube al sistema, junto con sus metadatos: nombre, tamaño, tipo de contenido y fecha de modificación.',
      'Automáticamente registramos datos de uso del sistema: acciones realizadas, fecha y hora de acceso, funciones utilizadas y registros de auditoría necesarios para el control de seguridad de la cuenta.',
      'No recopilamos datos de carácter sensible más allá de lo estrictamente necesario para el funcionamiento del sistema.'
    ]
  },
  {
    icon: Eye,
    title: 'Uso de los Datos',
    content: [
      'Los datos recopilados se utilizan exclusivamente para proveer, operar y mantener el servicio: almacenar y organizar sus archivos, gestionar su cuenta y generar los links de descarga que usted solicite compartir.',
      'Usamos información de uso del sistema para mejorar su funcionamiento, detectar errores, optimizar el rendimiento y desarrollar nuevas funcionalidades que beneficien a los usuarios.',
      'Podemos usar datos de contacto para comunicar actualizaciones importantes del sistema, avisos de seguridad o cambios en los términos del servicio. No enviamos comunicaciones de marketing no solicitadas.',
      'Los datos de auditoría y logs de actividad se usan para detectar y prevenir accesos no autorizados y abusos del sistema, garantizando la integridad de sus archivos.',
      'Nunca utilizamos sus datos para publicidad de terceros ni los compartimos con fines comerciales ajenos a la operación del sistema.'
    ]
  },
  {
    icon: Lock,
    title: 'Almacenamiento y Seguridad',
    content: [
      'Todos los datos se transmiten mediante protocolos HTTPS/TLS cifrados. Los archivos se almacenan en un bucket privado, accesibles únicamente mediante URLs firmadas de corta duración generadas por el propio sistema.',
      'Implementamos autenticación basada en tokens JWT con expiración controlada, autenticación de doble factor opcional, control de sesiones activas y bloqueo automático tras intentos de acceso fallidos consecutivos.',
      'El control de acceso basado en roles garantiza que cada usuario solo pueda ver y modificar los archivos correspondientes a sus permisos asignados, minimizando la exposición de información.',
      'Realizamos copias de seguridad automáticas y regulares de todos los datos del sistema. Se recomienda al administrador del sistema mantener respaldos adicionales en infraestructura propia.',
      'Ante cualquier incidente de seguridad que pueda comprometer datos de usuarios, notificaremos a los afectados en el menor tiempo posible y tomaremos las medidas correctivas necesarias.'
    ]
  },
  {
    icon: Cookie,
    title: 'Cookies y Sesiones',
    content: [
      'El sistema utiliza tokens de sesión almacenados localmente en el navegador para mantener la sesión activa del usuario autenticado.',
      'Las preferencias del usuario (tema visual, idioma, configuraciones de pantalla) se almacenan localmente para mejorar la experiencia de uso en cada inicio de sesión.',
      'No utilizamos cookies de rastreo de terceros ni tecnologías de seguimiento publicitario. Las únicas cookies funcionales son las necesarias para la autenticación y las preferencias del usuario.',
      'Las sesiones tienen un tiempo de expiración configurable. El sistema puede cerrar sesiones inactivas automáticamente como medida de seguridad según la configuración del administrador.'
    ]
  },
  {
    icon: UserCheck,
    title: 'Derechos del Usuario',
    content: [
      'Acceso: puede solicitar en cualquier momento una copia de los datos personales que el sistema tiene registrados sobre usted, incluyendo el historial de actividad de su cuenta.',
      'Rectificación: tiene derecho a corregir cualquier dato personal incorrecto o desactualizado desde su propia página de Preferencias, o solicitándolo a un administrador.',
      'Eliminación: puede solicitar la eliminación de sus datos personales y de los archivos asociados a su cuenta. Conservaremos únicamente los datos que la ley obligue a retener.',
      'Portabilidad: tiene derecho a descargar sus archivos y recibir sus datos en un formato estructurado y legible para transferirlos a otro sistema si lo requiere.',
      'Para ejercer cualquiera de estos derechos, comuníquese con el administrador de su sistema o escríbanos directamente (ver sección de Contacto).'
    ]
  },
  {
    icon: Mail,
    title: 'Contacto',
    content: [
      'Si tiene preguntas sobre esta Política de Privacidad, sobre el manejo de sus datos o desea ejercer alguno de sus derechos, puede escribirnos a wolfgrimm.wd@gmail.com.',
      'Nos comprometemos a responder cualquier consulta relacionada con privacidad y protección de datos en un plazo razonable y a adoptar las medidas necesarias para resolver cualquier inconveniente.'
    ]
  }
]

export function PrivacyPage() {
  const navigate = useNavigate()

  return (
    <div className="min-h-screen w-full overflow-hidden relative bg-linear-to-br from-gray-50 via-brand-50/30 to-gray-50 dark:from-gray-950 dark:via-gray-900 dark:to-gray-950">
      {/* Patrón de fondo decorativo */}
      <div className="absolute inset-0 overflow-hidden">
        <div
          className="absolute inset-0 opacity-[0.03] dark:opacity-[0.05]"
          style={{
            backgroundImage: `
              linear-gradient(to right, currentColor 1px, transparent 1px),
              linear-gradient(to bottom, currentColor 1px, transparent 1px)
            `,
            backgroundSize: '60px 60px'
          }}
        />
        <div className="absolute -top-24 -left-24 w-96 h-96 bg-brand-500/10 dark:bg-brand-500/5 rounded-full blur-3xl" />
        <div className="absolute -bottom-24 -right-24 w-96 h-96 bg-brand-500/10 dark:bg-brand-500/5 rounded-full blur-3xl" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-linear-to-br from-brand-500/5 to-transparent dark:from-brand-500/3 rounded-full blur-3xl" />
      </div>

      {/* Floating Back Button */}
      <div className="fixed top-6 left-6 z-50">
        <Button
          variant="outline"
          size="sm"
          onClick={() => navigate('/login')}
          className="rounded-full shadow-lg hover:shadow-xl transition-all bg-white/15 dark:bg-white/10 backdrop-blur-[5px] border border-white/18"
        >
          <ArrowLeft className="h-4 w-4" />
        </Button>
      </div>

      {/* Hero Section */}
      <div className="relative container mx-auto px-4 py-24 md:py-32">
        <div className="max-w-3xl mx-auto text-center space-y-6">
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-primary-accent/10 border border-primary-accent/20">
            <Shield className="h-4 w-4 text-primary-accent" />
            <span className="text-sm font-medium text-primary-accent">Protección de Datos</span>
          </div>

          <h1 className="text-5xl md:text-6xl font-bold bg-linear-to-r from-foreground via-foreground to-muted-foreground bg-clip-text text-transparent">
            Política de Privacidad
          </h1>

          <p className="text-xl text-muted-foreground leading-relaxed">
            Cómo FileMeshy recopila, usa y protege
            su información y sus archivos.
          </p>

          <p className="text-sm text-muted-foreground/70">
            Última actualización: septiembre 2026
          </p>
        </div>
      </div>

      {/* Content Sections */}
      <div className="relative container mx-auto px-4 pb-24">
        <div className="max-w-4xl mx-auto space-y-6">
          {sections.map((section, index) => (
            <Card
              key={index}
              className="bg-card border border-border shadow-lg hover:shadow-xl hover:border-primary-accent/50 transition-all duration-300"
            >
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-3 text-xl">
                  <div className="w-10 h-10 rounded-xl bg-brand-100 dark:bg-brand-950 flex items-center justify-center shrink-0">
                    <section.icon className="h-5 w-5 text-primary-accent" />
                  </div>
                  {section.title}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 pt-0">
                {section.content.map((paragraph, pIndex) => (
                  <p key={pIndex} className="text-muted-foreground leading-relaxed">
                    {paragraph}
                  </p>
                ))}
              </CardContent>
            </Card>
          ))}

          {/* Commitment notice */}
          <Card className="bg-brand-50 dark:bg-brand-950/30 border border-brand-200 dark:border-brand-900">
            <CardContent className="py-6">
              <p className="text-center text-sm text-muted-foreground leading-relaxed">
                FileMeshy se compromete a respetar y proteger
                su privacidad. Al utilizar el sistema, usted confirma haber leído y comprendido
                esta Política de Privacidad y acepta las prácticas de datos aquí descritas.
              </p>
            </CardContent>
          </Card>
        </div>
      </div>

      <Separator className="container mx-auto" />

      {/* Footer */}
      <div className="relative py-8">
        <div className="container mx-auto px-4">
          <div className="flex flex-col sm:flex-row items-center justify-center gap-1 sm:gap-2 text-center text-sm text-muted-foreground">
            <span>© {new Date().getFullYear()} DTS Labs · FileMeshy es una marca de DTS Labs</span>
            <span className="hidden sm:inline text-muted-foreground/50">•</span>
            <span className="flex items-center gap-1">Desarrollado con <Heart className="h-4 w-4 text-red-500 animate-pulse" /> por DTS Labs</span>
          </div>
        </div>
      </div>
    </div>
  )
}
