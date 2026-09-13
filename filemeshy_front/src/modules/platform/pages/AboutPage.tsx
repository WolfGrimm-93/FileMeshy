import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Code2, FolderTree, Shield, Zap, Users, Share2, Heart, Mail, Phone, Sparkles, LogIn } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/ui/cards/Card'
import { Button } from '@/ui/buttons/Button'
import { Separator } from '@/ui/dividers/Separator'
import logoFileMeshy from '@/assets/images/logo-filemeshy-color.png'
import logoDtsLabs from '@/assets/images/logo-dtslabs-color.png'

export function AboutPage() {
  const navigate = useNavigate()

  const features = [
    {
      icon: FolderTree,
      title: 'Explorador de Archivos',
      description: 'Organizá tus archivos en carpetas anidadas, con búsqueda y papelera de reciclaje con restaurar.'
    },
    {
      icon: Share2,
      title: 'Compartir con Control',
      description: 'Generá links para compartir archivos o carpetas, con expiración opcional y revocación en cualquier momento.'
    },
    {
      icon: Shield,
      title: 'Seguro y Confiable',
      description: 'Arquitectura robusta con autenticación de doble factor y control de permisos basado en roles.'
    },
    {
      icon: Users,
      title: 'Multi-usuario',
      description: 'Sistema colaborativo con gestión de usuarios, roles y permisos personalizados.'
    },
    {
      icon: Zap,
      title: 'Vista Previa Instantánea',
      description: 'Mirá imágenes y documentos PDF directo desde el navegador, sin descargarlos primero.'
    },
    {
      icon: Heart,
      title: 'Hecho con Pasión',
      description: 'Desarrollado con las mejores prácticas y tecnologías modernas del mercado.'
    }
  ]

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
        <button
          onClick={() => navigate('/login')}
          className="flex items-center justify-center w-10 h-10 rounded-full shadow-lg hover:shadow-xl transition-all bg-muted border border-border text-foreground/80 hover:bg-muted"
        >
          <ArrowLeft className="h-4 w-4" />
        </button>
      </div>

      {/* Hero Section */}
      <div className="relative">
        <div className="relative container mx-auto px-4 py-24 md:py-32">
          <div className="max-w-4xl mx-auto text-center space-y-8">
            {/* Logo */}
            <div className="flex justify-center mb-6">
              <img src={logoFileMeshy} alt="FileMeshy" className="h-40 object-contain" />
            </div>

            {/* Title with Gradient */}
            <div className="space-y-4">
              <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-primary-accent/10 dark:bg-primary-accent/20 border border-primary-accent/20">
                <Sparkles className="h-4 w-4 text-primary-accent" />
                <span className="text-sm font-medium text-primary-accent">Almacenamiento de Archivos</span>
              </div>

              <h1 className="text-5xl md:text-7xl font-bold bg-linear-to-r from-foreground via-foreground to-muted-foreground bg-clip-text text-transparent">
                FileMeshy
              </h1>

              <p className="text-xl md:text-2xl text-muted-foreground max-w-2xl mx-auto leading-relaxed">
                Guardá, organizá y compartí tus archivos desde cualquier lugar
              </p>
            </div>

            <div className="flex flex-wrap justify-center gap-4 pt-6">
              <Button
                size="lg"
                buttonStyle="solid"
                variant="primary"
                shadow="lg"
                leftIcon={<LogIn className="h-4 w-4" />}
                onClick={() => navigate('/login')}
              >
                Iniciar Sesión
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* Features Section */}
      <div className="relative container mx-auto px-4 pt-12 pb-24">
        <div className="max-w-6xl mx-auto space-y-12">
          <div className="text-center space-y-4">
            <h2 className="text-4xl md:text-5xl font-bold">
              Todo tu Contenido, en un Solo Lugar
            </h2>
            <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
              Todo lo que necesitas para guardar, organizar y compartir tus archivos
            </p>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {features.map((feature, index) => (
              <Card
                key={index}
                className="group bg-card border border-border shadow-lg hover:shadow-xl hover:border-primary-accent/50 transition-all duration-300"
              >
                <CardHeader>
                  <div className="w-14 h-14 rounded-2xl bg-linear-to-br from-primary-accent/10 to-primary-accent/5 dark:from-primary-accent/20 dark:to-primary-accent/10 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform duration-300">
                    <feature.icon className="h-7 w-7 text-primary-accent" />
                  </div>
                  <CardTitle className="text-xl">{feature.title}</CardTitle>
                </CardHeader>
                <CardContent>
                  <CardDescription className="text-base leading-relaxed">
                    {feature.description}
                  </CardDescription>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </div>

      <Separator className="container mx-auto" />

      {/* Developer Section */}
      <div className="relative container mx-auto px-4 py-24">
        <div className="max-w-5xl mx-auto">
          <Card className="bg-card border border-border shadow-2xl">
            <CardHeader className="text-center space-y-6 pt-12">
              <div className="flex justify-center">
                <img src={logoDtsLabs} alt="DTS Labs" className="h-40 object-contain" />
              </div>

              <div className="space-y-2">
                <CardTitle className="text-4xl md:text-5xl">DTS Labs</CardTitle>
                <CardDescription className="text-xl">
                  Digital Technology Services Labs
                </CardDescription>
                <p className="text-sm text-muted-foreground">República Dominicana</p>
              </div>
            </CardHeader>

            <CardContent className="space-y-8 pb-12">
              <p className="text-center text-muted-foreground text-lg leading-relaxed max-w-3xl mx-auto px-6">
                Empresa dominicana especializada en soluciones tecnológicas para negocios.
                Desarrollamos aplicaciones web modernas, herramientas de gestión y productos
                digitales como FileMeshy, pensados para simplificar el trabajo diario de
                equipos y personas.
              </p>

              <Separator />

              {/* Tech Stack */}
              <div className="space-y-6">
                <h3 className="text-2xl font-semibold text-center flex items-center justify-center gap-2">
                  <Code2 className="h-6 w-6 text-primary-accent" />
                  Stack Tecnológico
                </h3>
                <div className="flex flex-wrap justify-center gap-3 px-6">
                  {['React 19', 'TypeScript', 'Tailwind CSS', 'Python', 'FastAPI', 'PostgreSQL', 'Docker'].map((tech) => (
                    <div
                      key={tech}
                      className="px-6 py-3 rounded-xl bg-muted border border-border hover:border-primary-accent/50 transition-all duration-300 hover:-translate-y-1"
                    >
                      <span className="text-sm font-semibold">{tech}</span>
                    </div>
                  ))}
                </div>
              </div>

              <Separator />

              {/* Contact Links */}
              <div className="space-y-6">
                <h3 className="text-2xl font-semibold text-center">Contáctanos</h3>
                <div className="flex flex-wrap justify-center gap-4">
                  <a
                    href="mailto:wolfgrimm.wd@gmail.com"
                    className="inline-flex items-center gap-2 px-5 py-3 rounded-md border-2 border-input text-foreground/80 hover:bg-muted font-medium transition-all duration-200 text-base"
                  >
                    <Mail className="h-5 w-5" />
                    wolfgrimm.wd@gmail.com
                  </a>
                  <a
                    href="tel:+18495061464"
                    className="inline-flex items-center gap-2 px-5 py-3 rounded-md border-2 border-input text-foreground/80 hover:bg-muted font-medium transition-all duration-200 text-base"
                  >
                    <Phone className="h-5 w-5" />
                    849-506-1464
                  </a>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

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
