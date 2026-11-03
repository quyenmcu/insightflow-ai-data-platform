import type {Metadata} from 'next';
export const metadata:Metadata={title:'InsightFlow · Commerce analytics',description:'Verified historical commerce analytics and an evidence-based AI assistant.'};
export default function Layout({children}:{children:React.ReactNode}){return <html lang="en"><body>{children}</body></html>;}
