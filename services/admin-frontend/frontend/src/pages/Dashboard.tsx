import { useQuery } from '@tanstack/react-query'
import { apiClient } from '@/api/client'
import { Card, CardContent, CardHeader, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { useAuthStore } from '@/stores/authStore'

interface PlatformMetrics {
  total_customers: number
  active_instances: number
  total_instances: number
  revenue_mrr: number
  system_status: {
    user_service: string
    billing_service: string
    instance_service: string
    database_service: string
  }
}

interface Customer {
  id: string
  email: string
  full_name: string | null
  status: string
  created_at: string
  total_instances: number
}

export default function Dashboard() {
  const user = useAuthStore((state) => state.user)
  const logout = useAuthStore((state) => state.logout)

  const { data: metrics, isLoading: metricsLoading } = useQuery({
    queryKey: ['platform-metrics'],
    queryFn: async () => {
      const response = await apiClient.get<PlatformMetrics>('/admin/metrics')
      return response.data
    },
    refetchInterval: 30000, // Refresh every 30s
  })

  const { data: customers, isLoading: customersLoading } = useQuery({
    queryKey: ['customers'],
    queryFn: async () => {
      const response = await apiClient.get<Customer[]>('/admin/customers')
      return response.data
    },
  })

  const handleLogout = () => {
    logout()
    window.location.href = '/login'
  }

  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case 'running':
      case 'active':
      case 'healthy':
        return 'text-emerald-400'
      case 'stopped':
      case 'paused':
        return 'text-amber'
      case 'error':
      case 'terminated':
      case 'unhealthy':
        return 'text-red-400'
      default:
        return 'text-muted-foreground'
    }
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-electric/20 bg-background/80 backdrop-blur-sm sticky top-0 z-50">
        <div className="container mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-2 h-2 bg-electric rounded-full animate-pulse" />
              <h1 className="text-2xl font-bold bg-gradient-to-r from-electric to-amber bg-clip-text text-transparent">
                SaaSOdoo Admin
              </h1>
            </div>
            <div className="flex items-center gap-4">
              <div className="text-sm">
                <span className="text-muted-foreground font-mono">Logged in as:</span>{' '}
                <span className="text-electric font-medium">{user?.email}</span>
              </div>
              <Button variant="outline" size="sm" onClick={handleLogout}>
                Logout
              </Button>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="container mx-auto px-6 py-8">
        {/* Platform Metrics */}
        <div className="mb-8">
          <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
            <span className="w-1 h-5 bg-electric rounded-full" />
            Platform Overview
          </h2>

          {metricsLoading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {[...Array(4)].map((_, i) => (
                <Card key={i} className="animate-pulse">
                  <CardHeader>
                    <div className="h-4 bg-muted rounded w-1/2" />
                  </CardHeader>
                  <CardContent>
                    <div className="h-8 bg-muted rounded w-3/4" />
                  </CardContent>
                </Card>
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              <Card className="border-electric/30">
                <CardHeader className="pb-2">
                  <CardDescription>Total Customers</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="text-3xl font-bold font-mono text-electric">
                    {metrics?.total_customers || 0}
                  </div>
                </CardContent>
              </Card>

              <Card className="border-emerald-500/30">
                <CardHeader className="pb-2">
                  <CardDescription>Active Instances</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="text-3xl font-bold font-mono text-emerald-400">
                    {metrics?.active_instances || 0}
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">
                    of {metrics?.total_instances || 0} total
                  </p>
                </CardContent>
              </Card>

              <Card className="border-amber/30">
                <CardHeader className="pb-2">
                  <CardDescription>Monthly Revenue</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="text-3xl font-bold font-mono text-amber">
                    ${metrics?.revenue_mrr?.toLocaleString() || 0}
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">MRR</p>
                </CardContent>
              </Card>

              <Card className="border-electric/30">
                <CardHeader className="pb-2">
                  <CardDescription>System Health</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-1 text-sm font-mono">
                    {metrics?.system_status ? (
                      Object.entries(metrics.system_status).map(([service, status]) => (
                        <div key={service} className="flex justify-between">
                          <span className="text-muted-foreground">{service}:</span>
                          <span className={getStatusColor(status)}>{status}</span>
                        </div>
                      ))
                    ) : (
                      <div className="text-muted-foreground">Loading...</div>
                    )}
                  </div>
                </CardContent>
              </Card>
            </div>
          )}
        </div>

        {/* Recent Customers */}
        <div>
          <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
            <span className="w-1 h-5 bg-amber rounded-full" />
            Recent Customers
          </h2>

          {customersLoading ? (
            <Card>
              <CardContent className="pt-6">
                <div className="space-y-4">
                  {[...Array(5)].map((_, i) => (
                    <div key={i} className="animate-pulse flex gap-4">
                      <div className="h-4 bg-muted rounded flex-1" />
                      <div className="h-4 bg-muted rounded w-24" />
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardContent className="pt-6">
                {customers && customers.length > 0 ? (
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead>
                        <tr className="border-b border-electric/20">
                          <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground uppercase tracking-wide">
                            Email
                          </th>
                          <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground uppercase tracking-wide">
                            Name
                          </th>
                          <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground uppercase tracking-wide">
                            Instances
                          </th>
                          <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground uppercase tracking-wide">
                            Status
                          </th>
                          <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground uppercase tracking-wide">
                            Created
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {customers.slice(0, 10).map((customer) => (
                          <tr
                            key={customer.id}
                            className="border-b border-border hover:bg-electric/5 transition-colors"
                          >
                            <td className="py-3 px-4 font-mono text-sm">{customer.email}</td>
                            <td className="py-3 px-4 text-sm">
                              {customer.full_name || (
                                <span className="text-muted-foreground italic">Not set</span>
                              )}
                            </td>
                            <td className="py-3 px-4 font-mono text-sm text-center">
                              {customer.total_instances}
                            </td>
                            <td className="py-3 px-4">
                              <span
                                className={`text-sm font-medium ${getStatusColor(customer.status)}`}
                              >
                                {customer.status}
                              </span>
                            </td>
                            <td className="py-3 px-4 text-sm text-muted-foreground font-mono">
                              {new Date(customer.created_at).toLocaleDateString()}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="text-center py-8 text-muted-foreground">
                    No customers found
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </div>
      </main>
    </div>
  )
}
