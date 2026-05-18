import React, { useEffect, useState } from "react";
// import { aboutLinksService } from "../services/firestoreService";
import { fetchUserProfile } from "../services/authService";
import {
  Facebook, Instagram, Youtube, Globe, Music,
  Building2, Globe as GlobeIcon, Target, Users, Shield, TrendingUp,
  Award, Package, MessageCircle, Mail, Phone, MapPin, ExternalLink
} from 'lucide-react';

type LinkItem = {
  id: string;
  type: "facebook" | "instagram" | "youtube" | "tiktok" | "website" | "email" | "phone" | "location";
  url: string;
  createdAt: string;
};

const iconFor = (type: string) => {
  switch (type) {
    case "facebook": return <Facebook className="w-5 h-5" />;
    case "instagram": return <Instagram className="w-5 h-5" />;
    case "youtube": return <Youtube className="w-5 h-5" />;
    case "tiktok": return <Music className="w-5 h-5" />;
    case "website": return <Globe className="w-5 h-5" />;
    case "email": return <Mail className="w-5 h-5" />;
    case "phone": return <Phone className="w-5 h-5" />;
    case "location": return <MapPin className="w-5 h-5" />;
    default: return <Globe className="w-5 h-5" />;
  }
};

const getPlatformColor = (type: string, theme: 'light' | 'dark') => {
  const colors = {
    facebook: { light: "bg-blue-50/80 border-blue-200 text-blue-700", dark: "bg-blue-900/30 border-blue-700/50 text-blue-300" },
    instagram: {
      light: "bg-gradient-to-br from-pink-50/80 to-orange-50/80 border-pink-200/80 text-pink-700",
      dark: "bg-gradient-to-br from-pink-900/30 to-[var(--color-primary)]/30 border-pink-700/50 text-pink-300"
    },
    youtube: { light: "bg-red-50/80 border-red-200 text-red-700", dark: "bg-red-900/30 border-red-700/50 text-red-300" },
    tiktok: {
      light: "bg-gradient-to-br from-gray-900 to-gray-800 border-gray-800 text-white",
      dark: "bg-gradient-to-br from-gray-800 to-gray-900 border-gray-700 text-gray-100"
    },
    website: {
      light: "bg-gradient-to-br from-[var(--color-primary)]/80 to-blue-50/80 border-[var(--color-border)]/80 text-[var(--color-primary)]",
      dark: "bg-gradient-to-br from-[var(--color-primary)]/30 to-blue-900/30 border-[var(--color-border)]/50 text-[var(--color-primary)]"
    },
    email: { light: "bg-amber-50/80 border-amber-200 text-amber-700", dark: "bg-amber-900/30 border-amber-700/50 text-amber-300" },
    phone: { light: "bg-emerald-50/80 border-emerald-200 text-emerald-700", dark: "bg-emerald-900/30 border-emerald-700/50 text-emerald-300" },
    location: { light: "bg-[var(--color-surface-2)]/80 border-[var(--color-border)] text-[var(--color-primary)]", dark: "bg-[var(--color-primary)]/30 border-[var(--color-border)]/50 text-[var(--color-primary)]" }
  };

  return colors[type as keyof typeof colors]?.[theme] || colors.website[theme];
};

const getPlatformName = (type: string) => {
  const names: Record<string, string> = {
    facebook: "فيسبوك",
    instagram: "إنستغرام",
    youtube: "يوتيوب",
    tiktok: "تيك توك",
    website: "الموقع الإلكتروني",
    email: "البريد الإلكتروني",
    phone: "رقم الهاتف",
    location: "العنوان"
  };
  return names[type] || type;
};

export const AboutUs: React.FC = () => {
  const [links, setLinks] = useState<LinkItem[]>([]);
  const [isManager, setIsManager] = useState(false);
  const [theme, setTheme] = useState<'light' | 'dark'>('light');

  useEffect(() => {
    const load = async () => {
      const uid = localStorage.getItem("userId");
      const token = localStorage.getItem("token");
      if (uid && token) {
        const profile = await fetchUserProfile(uid);
        setIsManager(Boolean(profile && profile.role === "manager"));
      } else {
        setIsManager(false);
      }
    };
    load();

    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    setTheme(prefersDark ? 'dark' : 'light');

    const onStorage = () => load();
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  // قائمة الروابط التي طلبتها
  const defaultLinks: LinkItem[] = [
    { id: '1', type: 'instagram', url: 'https://www.instagram.com/katra_group?igsh=dmRtM3dkNmlrc2kw', createdAt: '' },
    { id: '2', type: 'tiktok', url: 'https://www.tiktok.com/@ktra.import.group?_r=1&_t=ZS-92CBUzi08iW', createdAt: '' },
    { id: '3', type: 'website', url: 'https://ktragroup.com', createdAt: '' },
    { id: '4', type: 'email', url: 'mailto:info@ktra.com', createdAt: '' },
  ];

  const displayLinks = links.length > 0 ? links : defaultLinks;

  // تقصير الروابط الطويلة للعرض
  const shortenUrl = (url: string, type: string) => {
    if (type === 'email') return url.replace('mailto:', '');
    if (type === 'phone') return url.replace('tel:', '');

    const cleanUrl = url.replace('https://', '').replace('http://', '');
    if (cleanUrl.length > 25) {
      return cleanUrl.substring(0, 22) + '...';
    }
    return cleanUrl;
  };

  return (
    <div className={`transition-colors duration-300 h-full ${theme === 'dark' ? 'bg-gradient-to-br from-gray-900 to-gray-800 text-gray-100' : 'bg-gradient-to-br from-blue-50 to-gray-50 text-gray-800'}`}>
      <div className="max-w-6xl mx-auto p-4 md:p-8">

        {/* رأس الصفحة */}
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-6 mb-10">
          <div>
            <div className="flex items-center gap-3 mb-4">
              <div className={`p-3 rounded-xl ${theme === 'dark' ? 'bg-blue-900/30' : 'bg-white shadow-md'}`}>
                <Building2 className={`w-8 h-8 ${theme === 'dark' ? 'text-blue-400' : 'text-blue-600'}`} />
              </div>
              <div>
                <h1 className="text-3xl md:text-4xl font-bold bg-gradient-to-r from-blue-600 to-[var(--color-primary)] bg-clip-text text-transparent">
                  شركة كترا KTRA للتجارة العالمية
                </h1>
                <p className={`text-lg mt-1 ${theme === 'dark' ? 'text-gray-300' : 'text-gray-600'}`}>
                  عراقة تتجاوز <span className="font-bold text-yellow-600">العشرين عاماً</span> في عالم الاستيراد
                </p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <div className={`px-4 py-2 rounded-full text-sm ${theme === 'dark' ? 'bg-gray-800 text-blue-300' : 'bg-blue-100 text-blue-700'}`}>
              <span className="flex items-center gap-1"><GlobeIcon className="w-4 h-4" /> عالمية النشاط</span>
            </div>
          </div>
        </div>

        {/* المحتوى الرئيسي */}
        <div className={`rounded-2xl shadow-xl overflow-hidden ${theme === 'dark' ? 'bg-gray-800/60 backdrop-blur-sm' : 'bg-white'}`}>
          <div className="p-6 md:p-8">
            {/* مقدمة الشركة */}
            <div className="mb-12">
              <p className={`text-lg leading-relaxed mb-6 ${theme === 'dark' ? 'text-gray-300' : 'text-gray-700'}`}>
                تُعدّ <span className="font-bold text-blue-600">شركة كترا KTRA للتجارة العالمية</span> امتداداً لتاريخ عريق يمتد لأكثر من عشرين عاماً في مجال <span className="font-semibold">التصنيع والاستيراد</span> من مصادر عالمية، لا سيما الصين وتركيا.
              </p>
              <p className={`text-lg leading-relaxed ${theme === 'dark' ? 'text-gray-300' : 'text-gray-700'}`}>
                نحن لا نستورد بضائع فحسب، بل نستورد ثقة وشراكات طويلة الأمد. نسوّق منتجاتنا في أسواق متنوعة حول العالم، مع تركيز خاص على منطقة <span className="font-semibold">الشرق الأوسط وأفريقيا</span>.
              </p>
            </div>

            {/* نقاط القوة في بطاقات */}
            <div className="mb-12">
              <h2 className="text-2xl font-bold mb-8 flex items-center gap-2">
                <Target className="w-6 h-6 text-blue-500" />
                ركائز تميزنا
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {[
                  { icon: <Award />, title: "خبرة متراكمة", desc: "أكثر من 20 عاماً في التجارة الدولية والاستيراد من أكبر الأسواق العالمية." },
                  { icon: <Package />, title: "شبكة موردين موثوقة", desc: "علاقات استراتيجية مع مصانع وموردين معتمدين يلتزمون بأعلى معايير الجودة العالمية." },
                  { icon: <TrendingUp />, title: "أسعار تنافسية", desc: "قدرة فريدة على خفض التكاليف وتقديم عروض سعرية تنافسية دون المساس بالجودة." },
                  { icon: <Shield />, title: "شهادات وجودة", desc: "ضمان حصول المنتجات على الشهادات الدولية اللازمة والالتزام بالمواصفات المطلوبة." },
                  { icon: <Users />, title: "دعم متكامل", desc: "فريق دعم فني وإداري يقدم حلولاً مخصصة ويسهل جميع الإجراءات اللوجستية والقانونية." },
                  { icon: <MessageCircle />, title: "خدمة عملاء", desc: "دعم متواصل وتواصل مباشر مع العملاء لتلبية احتياجاتهم وتقديم أفضل الحلول." },
                ].map((item, idx) => (
                  <div
                    key={idx}
                    className={`p-6 rounded-xl border transition-all duration-300 hover:scale-[1.02] ${theme === 'dark'
                      ? 'bg-gray-900/50 border-gray-700 hover:border-blue-500 hover:shadow-lg hover:shadow-blue-500/10'
                      : 'bg-gradient-to-br from-white to-gray-50/80 border-gray-200 hover:border-blue-300 hover:shadow-lg'
                      }`}
                  >
                    <div className={`p-3 rounded-lg w-fit mb-4 ${theme === 'dark' ? 'bg-blue-900/30 text-blue-400' : 'bg-blue-100 text-blue-600'}`}>
                      {item.icon}
                    </div>
                    <h3 className="font-bold text-xl mb-2">{item.title}</h3>
                    <p className={`text-sm ${theme === 'dark' ? 'text-gray-400' : 'text-gray-600'}`}>{item.desc}</p>
                  </div>
                ))}
              </div>
            </div>

            {/* قسم تواصل معنا - المحسّن */}
            <div className="mb-12">
              <div className="text-center mb-10">
                <h2 className="text-3xl font-bold mb-4 flex items-center justify-center gap-3">
                  <MessageCircle className={`w-8 h-8 ${theme === 'dark' ? 'text-blue-400' : 'text-blue-600'}`} />
                  <span className="bg-gradient-to-r from-blue-600 to-[var(--color-primary)] bg-clip-text text-transparent">
                    تواصل معنا
                  </span>
                </h2>
                <p className={`text-lg max-w-2xl mx-auto ${theme === 'dark' ? 'text-gray-400' : 'text-gray-600'}`}>
                  نحن هنا للإجابة على استفساراتكم وبناء شراكات ناجحة. تواصلوا معنا عبر أي من القنوات التالية:
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-2 xl:grid-cols-4 gap-5">
                {displayLinks.map((link) => (
                  <a
                    key={link.id}
                    href={link.url}
                    target={link.type === 'email' || link.type === 'phone' ? '_self' : '_blank'}
                    rel="noopener noreferrer"
                    className={`group relative overflow-hidden rounded-xl border transition-all duration-300 hover:-translate-y-1 hover:shadow-lg ${getPlatformColor(link.type, theme)}`}
                  >
                    <div className="relative p-5 flex flex-col items-center text-center h-full">
                      {/* الأيقونة الصغيرة */}
                      <div className={`p-3 rounded-xl mb-4 transition-all duration-300 group-hover:scale-105 ${theme === 'dark' ? 'bg-gray-800/40' : 'bg-white/60'}`}>
                        <div className={`${theme === 'dark' ? 'text-white' : ''} ${link.type === 'tiktok' && theme === 'light' ? 'text-white' : ''}`}>
                          {iconFor(link.type)}
                        </div>
                      </div>

                      {/* الاسم */}
                      <h3 className="text-lg font-bold mb-2">{getPlatformName(link.type)}</h3>

                      {/* الرابط المختصر */}
                      <p className={`text-xs mt-1 truncate w-full px-2 ${theme === 'dark' ? 'text-gray-400' : link.type === 'tiktok' && theme === 'light' ? 'text-gray-200' : 'text-gray-600'}`}>
                        {shortenUrl(link.url, link.type)}
                      </p>

                      {/* زر الإجراء الصغير */}
                      <div className={`mt-3 px-3 py-1.5 rounded-full text-xs font-medium transition-all duration-300 flex items-center gap-1 ${theme === 'dark'
                        ? 'bg-gray-800 text-gray-300 group-hover:bg-gray-700'
                        : link.type === 'tiktok'
                          ? 'bg-gray-800 text-white group-hover:bg-gray-700'
                          : 'bg-white text-gray-800 group-hover:bg-gray-100'
                        }`}>
                        {link.type === 'email' ? 'إرسال بريد' :
                          link.type === 'phone' ? 'اتصال' : 'زيارة'}
                        <ExternalLink className="w-3 h-3" />
                      </div>
                    </div>

                    {/* تأثير الزاوية الصغير */}
                    <div className={`absolute top-0 right-0 w-8 h-8 rounded-bl-xl transition-all duration-300 ${theme === 'dark' ? 'bg-blue-500/10' : 'bg-blue-100/50'}`}></div>
                  </a>
                ))}
              </div>
            </div>

            {/* تذييل الصفحة */}
            <div className={`mt-12 pt-8 border-t text-center ${theme === 'dark' ? 'border-gray-700 text-gray-500' : 'border-gray-200 text-gray-600'}`}>
              <p>© {new Date().getFullYear()} شركة كترا KTRA للتجارة العالمية. جميع الحقوق محفوظة.</p>
              <p className="text-sm mt-2">شريكك الموثوق في رحلة الاستيراد العالمية لأكثر من عقدين.</p>
              <div className="flex justify-center gap-4 mt-4">
                {displayLinks.map(link => (
                  <a
                    key={link.id}
                    href={link.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={`p-2 rounded-lg ${theme === 'dark' ? 'hover:bg-gray-800' : 'hover:bg-gray-100'}`}
                  >
                    {iconFor(link.type)}
                  </a>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AboutUs;