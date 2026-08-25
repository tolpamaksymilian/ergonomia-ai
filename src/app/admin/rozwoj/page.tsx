import { ProjectRoadmap } from "@/components/project/project-roadmap";
import { ProjectVersionCards } from "@/components/project/project-version-cards";
import { projectStatus } from "@/config/project-status";
export default function DevelopmentPage(){return <div className="dashboard-page"><header><p className="dashboard-eyebrow">System</p><h1 className="dashboard-title mt-2">Rozwój systemu</h1><p className="dashboard-muted mt-2">Wersje komponentów, gotowe moduły i kolejne etapy projektu.</p></header><ProjectVersionCards/><section className="dashboard-card p-5 sm:p-7"><ProjectRoadmap stages={projectStatus.stages} showProgress/></section></div>;}
