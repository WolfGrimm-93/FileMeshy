import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Heart, FileText, User, Lock, AlertTriangle, RefreshCw, Mail } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/ui/cards/Card'
import { Button } from '@/ui/buttons/Button'
import { Separator } from '@/ui/dividers/Separator'

const sections = [
  {
    icon: FileText,
    title: 'Uso del Servicio',
    content: [
      'FileMeshy es un servicio de almacenamiento y gestión de archivos en la nube. Al utilizarlo, el usuario acepta usarlo exclusivamente para fines legítimos de guardar, organizar y compartir su propio contenido.',
      'Queda prohibido subir o compartir a través del sistema contenido ilegal, malware, material que infrinja derechos de autor ajenos, o cualquier archivo que el usuario no tenga derecho a almacenar o distribuir.',
      'Los links de descarga generados por la función de "compartir" son responsabilidad de quien los crea: el usuario debe asegurarse de compartirlos únicamente con las personas a las que quiere darles acceso, y puede revocarlos en cualquier momento desde el propio sistema.',
      'No está permitido compartir credenciales de acceso ni permitir el uso de la cuenta a terceros no autorizados.'
    ]
  },
  {
    icon: User,
    title: 'Cuentas de Usuario',
    content: [
      'Cada cuenta de usuario es personal e intransferible. El titular es responsable de mantener la confidencialidad de sus credenciales de acceso (nombre de usuario y contraseña).',
      'En instalaciones con varios usuarios, el administrador del sistema es responsable de gestionar los roles y permisos, garantizando que cada usuario tenga acceso únicamente a lo necesario.',
      'En caso de pérdida o compromiso de credenciales, el usuario debe notificar al administrador del sistema de inmediato para que se tomen las medidas de seguridad pertinentes.',
      'El sistema registra un historial de auditoría de las acciones realizadas por cada usuario. Este registro puede ser consultado por administradores para fines de control interno.',
      'Las cuentas inactivas por períodos prolongados pueden ser desactivadas por el administrador del sistema como medida de seguridad.'
    ]
  },
  {
    icon: Lock,
    title: 'Propiedad Intelectual',
    content: [
      'Todo el software, código fuente, diseño, interfaces, logotipos y materiales asociados a FileMeshy son propiedad exclusiva de sus desarrolladores y están protegidos por las leyes de propiedad intelectual.',
      'Se otorga al usuario una licencia de uso limitada, no exclusiva e intransferible para utilizar el sistema conforme a estos términos. No se transfiere ningún derecho de propiedad intelectual sobre el software.',
      'Queda estrictamente prohibido copiar, modificar, distribuir, vender, sublicenciar, descompilar, realizar ingeniería inversa o intentar derivar el código fuente del sistema.',
      'Los archivos que el usuario sube al sistema son de su exclusiva propiedad. FileMeshy los almacena y facilita su gestión, pero no reclama ningún derecho sobre su contenido.'
    ]
  },
  {
    icon: AlertTriangle,
    title: 'Limitación de Responsabilidad',
    content: [
      'El sistema se proporciona "tal cual" y se realizan esfuerzos razonables para mantener su correcto funcionamiento. Sin embargo, no se garantiza que esté libre de errores o interrupciones.',
      'No somos responsables por pérdidas de datos derivadas de fallos de hardware, interrupciones del servicio de internet, cortes de electricidad u otras causas fuera de nuestro control directo.',
      'Aunque el sistema realiza copias de seguridad periódicas, el usuario es responsable de mantener copias adicionales de sus archivos más críticos fuera de la plataforma.',
      'En ningún caso la responsabilidad total derivada del uso del sistema excederá el monto pagado por el usuario en los últimos doce (12) meses por concepto de licencia o mantenimiento.',
      'No somos responsables por el contenido que un usuario comparte a través de un link generado por el sistema, ni por el uso que terceros hagan de un link compartido.'
    ]
  },
  {
    icon: RefreshCw,
    title: 'Modificaciones',
    content: [
      'Nos reservamos el derecho de modificar estos Términos de Servicio en cualquier momento. Los cambios entrarán en vigor a partir de su publicación en el sistema.',
      'Los usuarios serán notificados de cambios significativos a través del sistema. El uso continuado del sistema después de la notificación implica la aceptación de los nuevos términos.',
      'También podemos actualizar, mejorar o descontinuar funcionalidades del sistema con el fin de mejorar la experiencia del usuario o por requerimientos legales o técnicos.',
      'Si no está de acuerdo con alguna modificación a estos términos, debe discontinuar el uso del sistema y contactarnos para gestionar la cancelación de su cuenta.'
    ]
  },
  {
    icon: Mail,
    title: 'Contacto',
    content: [
      'Si tiene preguntas, dudas o inquietudes sobre estos Términos de Servicio, puede escribirnos a wolfgrimm.wd@gmail.com.',
      'Para reportar vulnerabilidades de seguridad o incidentes relacionados con el sistema, utilice el mismo canal de contacto indicando el detalle del problema encontrado.'
    ]
  }
]

export function TermsPage() {
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
            <FileText className="h-4 w-4 text-primary-accent" />
            <span className="text-sm font-medium text-primary-accent">Documento Legal</span>
          </div>

          <h1 className="text-5xl md:text-6xl font-bold bg-linear-to-r from-foreground via-foreground to-muted-foreground bg-clip-text text-transparent">
            Términos de Servicio
          </h1>

          <p className="text-xl text-muted-foreground leading-relaxed">
            Condiciones de uso del sistema FileMeshy.
            Lea detenidamente antes de utilizar el sistema.
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

          {/* Acceptance notice */}
          <Card className="bg-brand-50 dark:bg-brand-950/30 border border-brand-200 dark:border-brand-900">
            <CardContent className="py-6">
              <p className="text-center text-sm text-muted-foreground leading-relaxed">
                Al utilizar FileMeshy, usted confirma que ha leído, comprendido y
                aceptado estos Términos de Servicio en su totalidad. Si representa a una empresa,
                confirma que tiene autoridad para aceptar estos términos en nombre de dicha empresa.
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
