import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { getProfile } from '../api/users'
import { getRooms } from '../api/rooms'
import { getRequests } from '../api/requests'
import Layout from '../components/Layout'
import StatusBadge from '../components/StatusBadge'
import { BedDouble, ClipboardList, Users, AlertCircle, CheckCircle2, ArrowRight } from 'lucide-react'

export default function DashboardPage() {
  const { user, isStaff, updateUser } = useAuth()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')

  useEffect(() => {
    const load = async () => {
      try {
        if (isStaff) {
          const [rooms, requests] = await Promise.all([getRooms(), getRequests()])
          setData({
            rooms, requests,
            occupied:   rooms.filter(r => r.free_places < r.capacity).length,
            created:    requests.filter(r => r.status === 'created').length,
            inProgress: requests.filter(r => r.status === 'in_progress').length,
            done:       requests.filter(r => r.status === 'done').length,
          })
        } else {
          const [profile, requests] = await Promise.all([getProfile(user.id), getRequests()])
          setData({ profile, requests })
          // Синхронизируем room_id в localStorage если изменился
          if (profile.user && profile.user.room_id !== user.room_id) {
            updateUser({ ...user, room_id: profile.user.room_id })
          }
        }
      } catch (err) {
        const status = err?.response?.status
        if (status === 401) setLoadError('Сессия истекла. Пожалуйста, войдите снова.')
        else setLoadError('Не удалось загрузить данные. Проверьте соединение.')
      } finally { setLoading(false) }
    }
    load()
  }, [loading])

  if (loading) return <Layout><div className="spinner-wrap"><div className="spinner" /></div></Layout>
  if (loadError || !data) return (
    <Layout>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: 300, gap: 12 }}>
        <p style={{ color: '#ef4444', fontSize: 14 }}>{loadError || 'Ошибка загрузки'}</p>
        <button className="btn btn-primary btn-sm" onClick={() => { setLoadError(''); setLoading(true); }}>
          Попробовать снова
        </button>
      </div>
    </Layout>
  )

  return (
    <Layout>
      <div className="page-header">
        <h1 className="page-title">Привет, {user.full_name.split(' ')[1]} 👋</h1>
        <p className="page-subtitle">
          {new Date().toLocaleDateString('ru-RU', { weekday: 'long', day: 'numeric', month: 'long' })}
        </p>
      </div>
      {isStaff ? <StaffDash data={data} /> : <StudentDash data={data} />}
    </Layout>
  )
}

function StaffDash({ data }) {
  const stats = [
    { label: 'Всего комнат',  value: data.rooms.length,   Icon: BedDouble,    bg: '#eef2ff', color: '#6366f1' },
    { label: 'Занято',        value: data.occupied,        Icon: Users,        bg: '#f5f3ff', color: '#7c3aed' },
    { label: 'Новых заявок',  value: data.created,         Icon: AlertCircle,  bg: '#fffbeb', color: '#d97706' },
    { label: 'Выполнено',     value: data.done,            Icon: CheckCircle2, bg: '#f0fdf4', color: '#16a34a' },
  ]

  return (
    <div className="stack">
      <div className="grid-4">
        {stats.map(({ label, value, Icon, bg, color }) => (
          <div key={label} className="stat-card">
            <div className="stat-icon" style={{ background: bg }}>
              <Icon size={18} style={{ color }} />
            </div>
            <div>
              <div style={{ fontSize: 24, fontWeight: 700, color }}>{value}</div>
              <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 2 }}>{label}</div>
            </div>
          </div>
        ))}
      </div>

      <div className="grid-2">
        {/* Recent requests */}
        <div className="card">
          <div className="row-between mb-4">
            <span style={{ fontWeight: 600, color: '#1e293b' }}>Последние заявки</span>
            <Link to="/requests" style={{ fontSize: 12, color: '#6366f1', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 4 }}>
              Все <ArrowRight size={12} />
            </Link>
          </div>
          <div className="stack-sm">
            {data.requests.slice(0, 5).map(req => (
              <Link key={req.id} to={`/requests/${req.id}`} style={{ textDecoration: 'none', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 12px', borderRadius: 12, background: '#fafafa' }}
                onMouseEnter={e => e.currentTarget.style.background = '#f0f4ff'}
                onMouseLeave={e => e.currentTarget.style.background = '#fafafa'}>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 500, color: '#1e293b' }}>{req.category}</div>
                  <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 2 }}>{req.description.slice(0, 40)}…</div>
                </div>
                <StatusBadge status={req.status} />
              </Link>
            ))}
            {data.requests.length === 0 && <p style={{ color: '#94a3b8', fontSize: 13, textAlign: 'center', padding: '16px 0' }}>Заявок нет</p>}
          </div>
        </div>

        {/* Quick links */}
        <div className="card">
          <div style={{ fontWeight: 600, color: '#1e293b', marginBottom: 16 }}>Быстрые действия</div>
          <div className="stack-sm">
            {[
              { to: '/users',    label: 'Жильцы',    desc: 'Список, поиск, профили',     Icon: Users },
              { to: '/rooms',    label: 'Комнаты',   desc: 'Заселение и выселение',       Icon: BedDouble },
              { to: '/requests', label: 'Заявки',    desc: 'Все заявки студентов',        Icon: ClipboardList },
            ].map(({ to, label, desc, Icon }) => (
              <Link key={to} to={to} style={{ textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 12, padding: '10px 12px', borderRadius: 12 }}
                onMouseEnter={e => e.currentTarget.style.background = '#f8fafc'}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
                <div style={{ width: 36, height: 36, borderRadius: 10, background: '#eef2ff', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                  <Icon size={16} style={{ color: '#6366f1' }} />
                </div>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 500, color: '#1e293b' }}>{label}</div>
                  <div style={{ fontSize: 11, color: '#94a3b8' }}>{desc}</div>
                </div>
                <ArrowRight size={13} style={{ color: '#cbd5e1', marginLeft: 'auto' }} />
              </Link>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function StudentDash({ data }) {
  return (
    <div className="grid-2">
      <div className="card">
        <div className="row mb-4">
          <BedDouble size={15} style={{ color: '#a5b4fc' }} />
          <span style={{ fontWeight: 600, color: '#1e293b' }}>Моя комната</span>
        </div>
        {data.profile?.room ? (
          <>
            <div style={{ fontSize: 32, fontWeight: 700, color: '#1e293b' }}>№{data.profile.room.number}</div>
            <div className="row" style={{ marginTop: 8, gap: 8 }}>
              <StatusBadge status={data.profile.room.status} />
              <span style={{ fontSize: 12, color: '#94a3b8' }}>
                {data.profile.room.free_places}/{data.profile.room.capacity} мест свободно
              </span>
            </div>
            <div className="progress-bar" style={{ marginTop: 12 }}>
              <div className="progress-fill" style={{
                width: `${((data.profile.room.capacity - data.profile.room.free_places) / data.profile.room.capacity) * 100}%`,
                background: '#6366f1',
              }} />
            </div>
            <Link to={`/rooms/${data.profile.room.id}`} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, marginTop: 16, fontSize: 13, color: '#6366f1', textDecoration: 'none' }}>
              Подробнее <ArrowRight size={12} />
            </Link>
          </>
        ) : <p style={{ color: '#94a3b8', fontSize: 13 }}>Комната не назначена</p>}
      </div>

      <div className="card">
        <div className="row-between mb-4">
          <div className="row">
            <ClipboardList size={15} style={{ color: '#a5b4fc' }} />
            <span style={{ fontWeight: 600, color: '#1e293b' }}>Мои заявки</span>
          </div>
          <Link to="/requests" style={{ fontSize: 12, color: '#6366f1', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 4 }}>
            Все <ArrowRight size={12} />
          </Link>
        </div>
        {data.requests?.length > 0 ? (
          <div className="stack-sm">
            {data.requests.slice(0, 4).map(req => (
              <Link key={req.id} to={`/requests/${req.id}`}
                style={{ textDecoration: 'none', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid #f8fafc' }}>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 500, color: '#1e293b' }}>{req.category}</div>
                  <div style={{ fontSize: 11, color: '#94a3b8' }}>{new Date(req.created_at).toLocaleDateString('ru-RU')}</div>
                </div>
                <StatusBadge status={req.status} />
              </Link>
            ))}
          </div>
        ) : <p style={{ color: '#94a3b8', fontSize: 13 }}>Заявок нет</p>}
      </div>
    </div>
  )
}
